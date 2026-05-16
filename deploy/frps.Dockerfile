# frps 薄镜像：拉 fatedier 官方原生二进制，规避第三方镜像 TLS 不兼容问题。
# 与客户端 frpc（同样下载 fatedier 官方 release）配套使用，TLS 握手稳定。
FROM alpine:3.20

ARG FRP_VERSION=0.68.1
ARG TARGETARCH=amd64

RUN apk add --no-cache ca-certificates wget tar \
    && wget -q -O /tmp/frp.tar.gz \
        "https://github.com/fatedier/frp/releases/download/v${FRP_VERSION}/frp_${FRP_VERSION}_linux_${TARGETARCH}.tar.gz" \
    && tar -xzf /tmp/frp.tar.gz -C /tmp \
    && mv "/tmp/frp_${FRP_VERSION}_linux_${TARGETARCH}/frps" /usr/local/bin/frps \
    && chmod +x /usr/local/bin/frps \
    && rm -rf /tmp/frp.tar.gz "/tmp/frp_${FRP_VERSION}_linux_${TARGETARCH}" \
    && apk del wget tar

ENTRYPOINT ["/usr/local/bin/frps"]
CMD ["-c", "/etc/frp/frps.toml"]
