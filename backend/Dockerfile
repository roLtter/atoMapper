FROM golang:1.26-bookworm AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o /out/server ./cmd/server

FROM debian:bookworm-slim
WORKDIR /app
COPY --from=build /out/server /app/server
EXPOSE 8080
CMD ["/app/server"]
