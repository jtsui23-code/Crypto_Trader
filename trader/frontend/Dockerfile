# Use Node image
FROM node:20-alpine

WORKDIR /app

# Copy dependency files first to leverage Docker layer caching
COPY package.json package-lock.json ./

# Install dependencies
RUN npm install

# Copy the rest of your frontend source code
COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host"]