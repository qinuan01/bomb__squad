#!/bin/sh
set -e

echo "===> 🔧 安装编译依赖..."
apk add --no-cache build-base wget tar make gcc g++ musl-dev \
    zlib-dev openssl-dev bzip2-dev readline-dev sqlite-dev

echo "===> 📦 下载 Python 2.7.18 源码..."
wget https://www.python.org/ftp/python/2.7.18/Python-2.7.18.tgz -O Python-2.7.18.tgz
tar -xzf Python-2.7.18.tgz
cd Python-2.7.18

echo "===> ⚙️ 配置编译选项..."
./configure --prefix=/usr/local --enable-shared --without-ensurepip

echo "===> 🧱 开始编译（可能需要几分钟）..."
make -j1
make install

echo "===> 🧩 配置动态库..."
echo "/usr/local/lib" > /etc/ld.so.conf
ldconfig

echo "===> 🔗 创建命令软链接..."
ln -sf /usr/local/bin/python2 /usr/bin/python2
ln -sf /usr/local/bin/python2 /usr/bin/python

echo "===> 🧼 清理..."
cd ..
rm -rf Python-2.7.18*
swapoff /swapfile 2>/dev/null || true

echo "===> ✅ 安装完成！"
python2 --version
