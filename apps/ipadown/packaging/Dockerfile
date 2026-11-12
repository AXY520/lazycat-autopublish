# syntax=docker/dockerfile:1.7
# ---------- 构建 ----------
FROM rust:1-bookworm AS builder
ARG TARGETARCH
WORKDIR /app
COPY Cargo.toml Cargo.lock ./
COPY crates ./crates
RUN --mount=type=cache,id=ipadown-cargo-registry,target=/usr/local/cargo/registry,sharing=locked \
    --mount=type=cache,id=ipadown-target-${TARGETARCH},target=/app/target,sharing=locked \
    cargo build --locked --release -p ipadown-web \
    && cp /app/target/release/ipadown-web /tmp/ipadown-web

# ---------- 运行 ----------
FROM debian:bookworm-slim
ARG TARGETARCH
ARG IPATOOL_VERSION=2.8.1
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*
# Apple Root CA：gsa.apple.com（ipatool 2.8 登录/设备证明）证书链的根；Debian/Mozilla
# 信任库不含 Apple 根，而 ipatool 自带的下载兜底地址固定返回 403。
COPY certs/apple-root-ca.pem /usr/local/share/ca-certificates/apple-root-ca.crt
RUN update-ca-certificates
# ipatool：SAP 签名登录/下载依赖（2026-08 起苹果强制 X-Apple-ActionSignature）
# 2.7.0 修复 redownload 请求被苹果 403 拒绝（空响应体）的问题
RUN arch="${TARGETARCH:-amd64}" \
    && case "$arch" in \
         amd64) expected="c5a7d35d98a0ac41fbb9d21c19437c3e6006c6e32556f484d09ed26872f9c283" ;; \
         arm64) expected="64dc6311acbd92f8165fe382ee86852f520b23355dae65933cb0f60177357116" ;; \
         *) echo "unsupported architecture: $arch" >&2; exit 1 ;; \
       esac \
    && curl -sfL --retry 5 --retry-all-errors --retry-delay 5 \
         "https://github.com/majd/ipatool/releases/download/v${IPATOOL_VERSION}/ipatool-${IPATOOL_VERSION}-linux-${arch}.tar.gz" -o /tmp/ipatool.tgz \
    && echo "$expected  /tmp/ipatool.tgz" | sha256sum -c - \
    && tar xzf /tmp/ipatool.tgz -C /tmp \
    && mv "/tmp/bin/ipatool-${IPATOOL_VERSION}-linux-${arch}" /usr/local/bin/ipatool \
    && chmod +x /usr/local/bin/ipatool \
    && rm /tmp/ipatool.tgz
COPY --from=builder /tmp/ipadown-web /usr/local/bin/ipadown-web

ENV IPADOWN_DATA_DIR=/data \
    PORT=8080
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD curl -sf http://localhost:${PORT}/healthz || exit 1

CMD ["ipadown-web"]
