import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import requests
from datetime import datetime
from sklearn.preprocessing import MinMaxScaler
from sklearn.metrics import mean_absolute_error

# ---------------------------------------------------------------------------
# TensorFlow / Keras import guard
# ---------------------------------------------------------------------------

# Fail early with a clear install message rather than an obscure AttributeError
try:
    import tensorflow as tf
    from tensorflow.keras.models import Sequential
    from tensorflow.keras.layers import LSTM, Dense, Dropout
    from tensorflow.keras.callbacks import EarlyStopping
except ImportError:
    sys.exit("TensorFlow not found. Install with:  pip install tensorflow")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Number of calendar days of SOL/USD history to pull from CoinGecko
DAYS = 365

# Number of past days the LSTM looks at when predicting the next price
SEQ_LEN = 60

# Maximum training epochs (early stopping will usually halt before this)
EPOCHS = 80

# Number of samples processed in each gradient-descent step
BATCH_SIZE = 32

# How many days ahead to forecast after the last known price
FORECAST_DAYS = 14

# Fraction of data used for training; remainder is held out for evaluation
TRAIN_RATIO = 0.80

# Random seed for NumPy and TensorFlow (ensures reproducible results)
SEED = 42

np.random.seed(SEED)
tf.random.set_seed(SEED)


# ---------------------------------------------------------------------------
# Other model settings available for future experimentation (not yet active)
# ---------------------------------------------------------------------------
# UNITS_LAYER_1   = 256   # Increase LSTM units for a larger capacity model
# UNITS_LAYER_2   = 128   # Second LSTM layer size
# DROPOUT_RATE    = 0.30  # Higher dropout for stronger regularisation
# LEARNING_RATE   = 1e-4  # Custom Adam learning rate (default 1e-3)
# CONFIDENCE_BAND = 0.10  # Widen forecast ribbon to ±10% instead of ±7%


"""
Function Name:
    fetch_sol_prices

Parameters:
    days (int):
        Number of historical days to request from CoinGecko.
        Defaults to DAYS (365).

Return:
    pd.DataFrame:
        Single-column DataFrame indexed by UTC date with column "price"
        containing the daily closing SOL/USD price.

Function Description:
    Calls the free CoinGecko /coins/solana/market_chart endpoint — no
    API key required. Converts the returned millisecond timestamps to
    a DatetimeIndex and sorts ascending so the data is ready for
    sequential modelling.
"""
def fetch_sol_prices(days: int = DAYS) -> pd.DataFrame:
    print(f"[*] Fetching {days}-day SOL/USD history from CoinGecko ...")

    url = (
        "https://api.coingecko.com/api/v3/coins/solana/market_chart"
        f"?vs_currency=usd&days={days}&interval=daily"
    )

    resp = requests.get(url, timeout=20)
    resp.raise_for_status()

    # CoinGecko returns [[timestamp_ms, price], ...]
    prices = resp.json()["prices"]

    df = pd.DataFrame(prices, columns=["timestamp", "price"])
    df["date"] = pd.to_datetime(df["timestamp"], unit="ms")
    df = df.set_index("date")[["price"]].sort_index()

    print(
        f"    -> {len(df)} data points  |  "
        f"{df.index[0].date()} -> {df.index[-1].date()}"
    )
    return df


# ---------------------------------------------------------------------------
# Sequence construction
# ---------------------------------------------------------------------------

"""
Function Name:
    make_sequences

Parameters:
    scaled (np.ndarray):
        2-D array of shape (n_samples, 1) containing MinMax-scaled prices.
    seq_len (int):
        Look-back window length (number of past days per sample).

Return:
    tuple[np.ndarray, np.ndarray]:
        X -- shape (n_sequences, seq_len, 1), the input windows.
        y -- shape (n_sequences,), the target price for each window.

Function Description:
    Converts a 1-D scaled price series into supervised learning pairs.
    Each sample X[i] is a window of seq_len consecutive prices and
    y[i] is the price immediately following that window.
    The leading dimension of X is expanded to (samples, timesteps, features)
    to match the input shape expected by Keras LSTM layers.
"""
def make_sequences(scaled: np.ndarray, seq_len: int):
    X, y = [], []

    for i in range(seq_len, len(scaled)):
        X.append(scaled[i - seq_len:i, 0])    # look-back window
        y.append(scaled[i, 0])                 # next-step target

    # Add the feature dimension required by LSTM: (samples, timesteps, 1)
    return np.array(X)[..., np.newaxis], np.array(y)


# ---------------------------------------------------------------------------
# Model definition
# ---------------------------------------------------------------------------

"""
Function Name:
    build_model

Parameters:
    seq_len (int):
        Number of timesteps in each input sequence.
        Used to set the LSTM input_shape.

Return:
    tensorflow.keras.Sequential:
        Compiled but untrained LSTM model.

Function Description:
    Constructs a two-layer stacked LSTM with dropout regularisation
    followed by a dense hidden layer and a single linear output neuron.

    Architecture:
        LSTM(128, return_sequences=True)  -- captures long-range patterns
        Dropout(0.20)                     -- reduces overfitting
        LSTM(64,  return_sequences=False) -- distils sequence to a vector
        Dropout(0.20)
        Dense(32, relu)                   -- non-linear feature mixing
        Dense(1)                          -- scalar price prediction

    Compiled with the Adam optimiser and mean-squared-error loss, which
    penalises large price deviations more heavily than small ones.
"""
def build_model(seq_len: int) -> Sequential:
    model = Sequential([
        LSTM(128, return_sequences=True, input_shape=(seq_len, 1)),
        Dropout(0.20),
        LSTM(64, return_sequences=False),
        Dropout(0.20),
        Dense(32, activation="relu"),
        Dense(1),
    ])

    model.compile(optimizer="adam", loss="mse")
    return model


# ---------------------------------------------------------------------------
# Trend signal
# ---------------------------------------------------------------------------

"""
Function Name:
    trend_signal

Parameters:
    current_price (float):
        The last known SOL/USD price (today's closing price).
    forecast_prices (np.ndarray):
        Array of FORECAST_DAYS predicted prices produced by the model.

Return:
    str:
        A human-readable trend label with direction emoji and percentage
        change over the forecast horizon.

Function Description:
    Compares the final forecast price against the current price to
    derive a directional bias signal:

        BULLISH  -- forecast end-price is more than +5% above current
        BEARISH  -- forecast end-price is more than -5% below current
        NEUTRAL  -- forecast end-price is within +/-5% of current

    The percentage change and FORECAST_DAYS count are embedded in the
    returned string so callers can display it without further formatting.
"""
def trend_signal(current_price: float, forecast_prices: np.ndarray) -> str:
    end_price  = forecast_prices[-1]
    change_pct = (end_price - current_price) / current_price * 100

    if change_pct > 5:
        return f"BULLISH  (+{change_pct:.1f}% over {FORECAST_DAYS}d forecast)"
    elif change_pct < -5:
        return f"BEARISH  ({change_pct:.1f}% over {FORECAST_DAYS}d forecast)"
    else:
        return f"NEUTRAL  ({change_pct:+.1f}% over {FORECAST_DAYS}d forecast)"


# ---------------------------------------------------------------------------
# Chart rendering
# ---------------------------------------------------------------------------

"""
Function Name:
    plot_results

Parameters:
    df (pd.DataFrame):
        Full historical price DataFrame returned by fetch_sol_prices.
    train_size (int):
        Number of rows used for training; determines where test predictions
        begin on the chart.
    predictions_inv (np.ndarray):
        Inverse-scaled LSTM predictions aligned to the test portion of df.
    forecast_dates (pd.DatetimeIndex):
        Future dates corresponding to each forecasted price.
    forecast_prices (np.ndarray):
        Inverse-scaled model output for the FORECAST_DAYS ahead window.
    scaler (MinMaxScaler):
        Fitted scaler -- retained in the signature for potential re-use
        by callers who need to transform additional series.
    mae (float):
        Mean absolute error on the test set, shown in the legend.

Return:
    None

Function Description:
    Produces and saves a two-panel dark-themed chart:

    Top panel -- price history:
        Blue line   : actual SOL/USD closing prices
        Red dashed  : LSTM test-set predictions with MAE in the label
        Green line  : FORECAST_DAYS forward price forecast
        Green band  : +/-7% confidence ribbon around the forecast
        Yellow line : vertical marker at today's date

    Bottom panel -- residuals:
        Green/red bars showing (actual - predicted) for the test period,
        giving a visual sense of where the model over- or under-shoots.

    The figure is saved to solana_lstm_forecast.png at 150 dpi and then
    displayed interactively via plt.show().
"""
def plot_results(
    df,
    train_size,
    predictions_inv,
    forecast_dates,
    forecast_prices,
    scaler,
    mae,
):
    actual = df["price"].values

    # Predictions start after the look-back window that follows the training split
    pred_start_idx = len(df) - len(predictions_inv)
    pred_dates     = df.index[pred_start_idx:]   # gives 74 dates to match 74 predictions

    # -----------------------------------------------------------------------
    # Figure and axes setup
    # -----------------------------------------------------------------------

    fig, (ax1, ax2) = plt.subplots(
        2, 1,
        figsize=(14, 10),
        gridspec_kw={"height_ratios": [3, 1]},
    )

    # Dark background consistent across figure and both axes
    fig.patch.set_facecolor("#0d1117")
    for ax in (ax1, ax2):
        ax.set_facecolor("#161b22")
        ax.tick_params(colors="#c9d1d9")
        ax.spines[:].set_color("#30363d")

    # -----------------------------------------------------------------------
    # Top panel -- actual vs predicted vs forecast
    # -----------------------------------------------------------------------

    ax1.plot(
        df.index, actual,
        color="#58a6ff", linewidth=1.5,
        label="Actual SOL/USD", alpha=0.9,
    )
    ax1.plot(
        pred_dates, predictions_inv,
        color="#f78166", linewidth=1.5, linestyle="--",
        label=f"LSTM prediction (MAE ${mae:.2f})",
    )
    ax1.plot(
        forecast_dates, forecast_prices,
        color="#3fb950", linewidth=2.5,
        label=f"{FORECAST_DAYS}-day forecast", zorder=5,
    )

    # Shaded +/-7% confidence band around the forecast line
    ax1.fill_between(
        forecast_dates,
        forecast_prices * 0.93,
        forecast_prices * 1.07,
        color="#3fb950", alpha=0.15,
        label="+/-7% confidence band",
    )

    # Vertical dotted line marking today (last known price date)
    ax1.axvline(
        df.index[-1],
        color="#e3b341", linewidth=1, linestyle=":", alpha=0.8,
        label="Today",
    )

    ax1.set_title(
        "Solana (SOL/USD) -- LSTM Price Trend",
        color="#e6edf3", fontsize=16, fontweight="bold", pad=14,
    )
    ax1.set_ylabel("Price (USD)", color="#c9d1d9", fontsize=12)
    ax1.legend(
        facecolor="#21262d", labelcolor="#c9d1d9",
        fontsize=9, loc="upper left",
    )
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
    ax1.xaxis.set_major_locator(mdates.MonthLocator())
    plt.setp(ax1.xaxis.get_majorticklabels(), rotation=30, ha="right")

    # -----------------------------------------------------------------------
    # Bottom panel -- prediction residuals (actual - predicted)
    # -----------------------------------------------------------------------

    residuals = actual[pred_start_idx:] - predictions_inv

    # Green bars where the model under-predicted; red where it over-predicted
    ax2.bar(
        pred_dates, residuals,
        color=np.where(residuals >= 0, "#3fb950", "#f78166"),
        alpha=0.7,
    )
    ax2.axhline(0, color="#c9d1d9", linewidth=0.8, linestyle="--")
    ax2.set_ylabel("Residual (USD)", color="#c9d1d9", fontsize=10)
    ax2.set_xlabel("Date", color="#c9d1d9", fontsize=11)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
    ax2.xaxis.set_major_locator(mdates.MonthLocator())
    plt.setp(ax2.xaxis.get_majorticklabels(), rotation=30, ha="right")

    plt.tight_layout(pad=2)

    out_path = "solana_lstm_forecast.png"
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    print(f"[*] Chart saved -> {out_path}")
    plt.show()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

"""
Function Name:
    main

Parameters:
    None

Return:
    None

Function Description:
    Orchestrates the full pipeline:

    1. Data fetch      -- pulls DAYS of SOL/USD daily closes from CoinGecko.
    2. Scaling         -- applies MinMaxScaler(0, 1) to stabilise LSTM training.
    3. Sequence build  -- converts the scaled series into (X, y) pairs with
                         SEQ_LEN look-back windows.
    4. Train/test split -- TRAIN_RATIO of rows for training; remainder for eval.
    5. Model training  -- fits the two-layer LSTM with early stopping on
                         val_loss (patience=10).
    6. Evaluation      -- inverse-transforms test predictions and computes MAE.
    7. Forecasting     -- autoregressively predicts FORECAST_DAYS ahead by
                         feeding each predicted step back as the next input.
    8. Console report  -- prints current price, end-of-forecast price, trend
                         signal, model MAE, and a day-by-day price table.
    9. Chart           -- calls plot_results to render and save the figure.
"""
def main():

    # -----------------------------------------------------------------------
    # 1. Fetch historical data
    # -----------------------------------------------------------------------

    df = fetch_sol_prices()

    # -----------------------------------------------------------------------
    # 2. Scale prices to [0, 1] -- required for stable LSTM gradient flow
    # -----------------------------------------------------------------------

    scaler = MinMaxScaler(feature_range=(0, 1))
    scaled = scaler.fit_transform(df[["price"]].values)

    # -----------------------------------------------------------------------
    # 3. Build train and test arrays
    # -----------------------------------------------------------------------

    train_size = int(len(scaled) * TRAIN_RATIO)

    train_data = scaled[:train_size]

    # Overlap the last SEQ_LEN training rows into test so the first test
    # window has a full look-back without any out-of-bounds indexing
    test_data = scaled[train_size - SEQ_LEN:]

    X_train, y_train = make_sequences(train_data, SEQ_LEN)
    X_test,  y_test  = make_sequences(test_data,  SEQ_LEN)

    print(f"[*] Train samples: {len(X_train)}  |  Test samples: {len(X_test)}")

    # -----------------------------------------------------------------------
    # 4. Train the LSTM
    # -----------------------------------------------------------------------

    print("[*] Training LSTM ...")

    model = build_model(SEQ_LEN)
    model.summary()

    # Stop early when validation loss stops improving to prevent overfitting
    early_stop = EarlyStopping(
        monitor="val_loss",
        patience=10,
        restore_best_weights=True,
    )

    model.fit(
        X_train, y_train,
        epochs=EPOCHS,
        batch_size=BATCH_SIZE,
        validation_split=0.10,   # hold out 10% of training data for val_loss
        callbacks=[early_stop],
        verbose=1,
    )

    # -----------------------------------------------------------------------
    # 5. Evaluate on the held-out test set
    # -----------------------------------------------------------------------

    pred_scaled      = model.predict(X_test)
    predictions_inv  = scaler.inverse_transform(pred_scaled).flatten()
    actual_test_inv  = scaler.inverse_transform(y_test.reshape(-1, 1)).flatten()

    mae = mean_absolute_error(actual_test_inv, predictions_inv)
    print(f"\n[*] Test MAE: ${mae:.4f}")

    # -----------------------------------------------------------------------
    # 6. Autoregressive forecast -- FORECAST_DAYS steps ahead
    # -----------------------------------------------------------------------

    # Seed the forecast with the last SEQ_LEN scaled prices
    last_seq = scaled[-SEQ_LEN:].reshape(1, SEQ_LEN, 1)

    future_scaled = []
    for _ in range(FORECAST_DAYS):
        nxt = model.predict(last_seq, verbose=0)[0, 0]
        future_scaled.append(nxt)

        # Slide the window forward by one step (drop oldest, append prediction)
        last_seq = np.append(last_seq[:, 1:, :], [[[nxt]]], axis=1)

    forecast_prices = scaler.inverse_transform(
        np.array(future_scaled).reshape(-1, 1)
    ).flatten()

    # Build the date index for the forecast period starting the day after today
    last_date      = df.index[-1]
    forecast_dates = pd.date_range(
        start=last_date + pd.Timedelta(days=1),
        periods=FORECAST_DAYS,
        freq="D",
    )

    # -----------------------------------------------------------------------
    # 7. Print trend report to console
    # -----------------------------------------------------------------------

    current_price = df["price"].iloc[-1]
    signal        = trend_signal(current_price, forecast_prices)

    print("\n" + "=" * 50)
    print("  SOLANA LSTM TREND REPORT")
    print("=" * 50)
    print(f"  Current price  : ${current_price:,.2f}")
    print(f"  {FORECAST_DAYS}-day forecast : ${forecast_prices[-1]:,.2f}")
    print(f"  Trend signal   : {signal}")
    print(f"  Model MAE      : ${mae:.2f}")
    print("=" * 50)
    print(f"\n  {'Date':<12}  {'Forecast Price':>14}")
    print(f"  {'-' * 12}  {'-' * 14}")
    for d, p in zip(forecast_dates, forecast_prices):
        print(f"  {d.strftime('%Y-%m-%d'):<12}  ${p:>13,.2f}")
    print()

    # -----------------------------------------------------------------------
    # 8. Render chart
    # -----------------------------------------------------------------------

    plot_results(
        df,
        train_size,
        predictions_inv,
        forecast_dates,
        forecast_prices,
        scaler,
        mae,
    )


if __name__ == "__main__":
    main()