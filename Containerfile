# Use the official Node.js 20 image as base
FROM node:20-alpine

# Set working directory
WORKDIR /app

# Copy the entire application code first
COPY . .

# Install dependencies with legacy peer deps to resolve React 19 compatibility issues
RUN npm install --legacy-peer-deps


# Create a non-root user
RUN addgroup -g 1001 -S nodejs
RUN adduser -S nextjs -u 1001

# Change ownership of the app directory to the nodejs user
RUN chown -R nextjs:nodejs /app

# Expose the port that Vite uses (as configured in vite.config.ts)
EXPOSE 8080

# Command to run the application in development mode
CMD ["npm", "run", "dev"]