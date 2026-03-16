# Use Node image
FROM node:20-alpine

# Set working directory
WORKDIR /app

# Install dependencies
COPY package*.json ./
RUN npm install

# Copy source code
COPY . .

# Expose Vite/CRA port (usually 5173 or 3000)
EXPOSE 5173

CMD ["npm", "run", "dev"]