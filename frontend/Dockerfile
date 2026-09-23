FROM node:20-alpine

ENV TZ=Asia/Jakarta \
    NEXT_TELEMETRY_DISABLED=1

WORKDIR /app

RUN apk add --no-cache tzdata \
    && cp /usr/share/zoneinfo/$TZ /etc/localtime \
    && echo $TZ > /etc/timezone

COPY package.json package-lock.json* ./
RUN npm install

COPY . .

EXPOSE 3000

CMD ["npm", "run", "dev"]
