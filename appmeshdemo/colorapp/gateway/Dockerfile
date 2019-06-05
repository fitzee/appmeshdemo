FROM golang:alpine AS builder

# Install git.
# Git is required for fetching the dependencies.
RUN apk update && apk add --no-cache git
RUN apk update && apk add --no-cache bash

# Copy the code from the host and compile it
WORKDIR $GOPATH/src/github.com/username/repo
COPY Gopkg.toml main.go ./
RUN go get -d -v
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -ldflags="-w -s" -o /app ./main.go

FROM scratch
COPY --from=builder /app ./
ENTRYPOINT ["./app"]
