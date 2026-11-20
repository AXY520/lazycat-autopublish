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
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl unzip \
    && rm -rf /var/lib/apt/lists/*
# Apple Root CA：gsa.apple.com（ipatool 2.8 登录/设备证明）证书链的根；Debian/Mozilla
# 信任库不含 Apple 根，而 ipatool 自带的下载兜底地址固定返回 403。
COPY certs/apple-root-ca.pem /usr/local/share/ca-certificates/apple-root-ca.crt
# 懒猫 exec 沙箱的 /etc/ssl 是只读挂载、看不到构建期的 update-ca-certificates 结果，
# 因此另生成一份只给 ipatool 用的合并证书包（SSL_CERT_FILE，见 crates/store/src/ipatool.rs）。
RUN mkdir -p /usr/local/share/ipatool \
    && { cat /etc/ssl/certs/ca-certificates.crt; cat /usr/local/share/ca-certificates/apple-root-ca.crt; } \
       > /usr/local/share/ipatool/ca-bundle.pem \
    && update-ca-certificates
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

# Unicorn：ipatool 2.8 登录/下载依赖的模拟器运行库（缓存布局见 crates/store/src/ipatool.rs）。
# 运行时从 PyPI 拉 wheel（约 16MB）在国内经常超过 ipatool 内置的 2 分钟超时，导致登录失败；
# 构建期预置并按官方发布的 SHA-256 校验，镜像站只作为传输通道。
RUN set -eu; \
    arch="${TARGETARCH:-amd64}"; \
    case "$arch" in \
      amd64) wheel="packages/e7/df/ded5e3684c2d7600b30cc8a7530277b8cb36644a1a9d34cade7ebb45604c/unicorn-2.1.4-cp37-abi3-manylinux_2_17_x86_64.manylinux2014_x86_64.whl"; \
             wheel_sha="9d6e6dea140560de4ebd8446661f7ef84a357d428c14a3ef09dacd306ec8c239"; \
             lib_sha="ddb196ec82b52e502c18e4a34478bf7b9f61c83c2ebaa95c74d8ded45a95da9c" ;; \
      arm64) wheel="packages/33/9f/32d41eb942221bcf4417cdc65537fc8b3bbbd6079d6c161e621f1dd4e94a/unicorn-2.1.4-cp37-abi3-manylinux_2_17_aarch64.manylinux2014_aarch64.whl"; \
             wheel_sha="bd1fb0c9af5f57e356d8a96928b4fe045b2e18f308ef23b481d5f970008aa722"; \
             lib_sha="a0b99458a82e268aee258205a40590411c3a9f28e42abf2942ce4e87b7d9ac65" ;; \
      *) echo "unsupported architecture: $arch" >&2; exit 1 ;; \
    esac; \
    for base in https://mirrors.aliyun.com/pypi https://mirrors.cloud.tencent.com/pypi https://pypi.tuna.tsinghua.edu.cn https://files.pythonhosted.org; do \
      rm -f /tmp/unicorn.whl; \
      if curl -sfL --retry 2 --retry-all-errors --retry-delay 3 --max-time 180 "$base/$wheel" -o /tmp/unicorn.whl; then break; fi; \
    done; \
    echo "$wheel_sha  /tmp/unicorn.whl" | sha256sum -c -; \
    dir="/usr/local/share/ipatool/unicorn/2.1.4/$lib_sha"; \
    mkdir -p "$dir"; \
    unzip -p /tmp/unicorn.whl unicorn/lib/libunicorn.so.2 > "$dir/libunicorn.so.2"; \
    echo "$lib_sha  $dir/libunicorn.so.2" | sha256sum -c -; \
    rm -f /tmp/unicorn.whl
COPY --from=builder /tmp/ipadown-web /usr/local/bin/ipadown-web

ENV IPADOWN_DATA_DIR=/data \
    PORT=8080
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD curl -sf http://localhost:${PORT}/healthz || exit 1

CMD ["ipadown-web"]
