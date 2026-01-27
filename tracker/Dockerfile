FROM golang:1.22-alpine AS builder

WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download

COPY main.go ./
RUN CGO_ENABLED=0 GOOS=linux go build -o spotify-tracker

FROM alpine:3.19
WORKDIR /app
COPY --from=builder /app/spotify-tracker .
CMD ["./spotify-tracker"]
