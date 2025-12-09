#!/bin/sh
Green="\\033[32m"
Red="\\033[31m"
Plain="\\033[0m"

set -e

case ${MIRRORS} in
"custom")
    # custom
    if [ -z "${CUSTOM_REPO+x}" ]; then
      echo -e "${Red} [ERR] 未配置自定义仓库链接！ ${Plain}"
      exit 1
    else
      echo -e "${Green} [INFO] 使用自定义仓库 ${Plain}"
      git remote set-url origin ${CUSTOM_REPO}
    fi
    ;;
"0")
    # https://github.com/
    echo -e "${Green} [INFO] 使用源-GitHub ${Plain}"
    git remote set-url origin https://github.com/Liu-cloud136/fans-medal-helper.git
    ;;
"1")
    # https://ghproxy.com/
    echo -e "${Green} [INFO] 使用镜像源-GHProxy ${Plain}"
    git remote set-url origin https://mirror.ghproxy.com/https://github.com/Liu-cloud136/fans-medal-helper.git
    ;;
"2")
    # https://hub.fastgit.xyz/
    echo -e "${Green} [INFO] 使用镜像源-FastGIT ${Plain}"
    git remote set-url origin https://hub.fastgit.xyz/Liu-cloud136/fans-medal-helper.git
    ;;
"3")
    # https://ghproxy.cn/
    echo -e "${Green} [INFO] 使用镜像源-GHProxyCN ${Plain}"
    git remote set-url origin https://ghproxy.cn/https://github.com/Liu-cloud136/fans-medal-helper.git
    ;;
"4")
    # https://gitclone.com/
    echo -e "${Green} [INFO] 使用镜像源-GitClone ${Plain}"
    git remote set-url origin https://gitclone.com/github.com/Liu-cloud136/fans-medal-helper.git
    ;;
*)
    echo -e "${Green} [INFO] 使用源-GitHub ${Plain}"
    git remote set-url origin https://github.com/Liu-cloud136/fans-medal-helper.git
    ;;
esac

# 重试拉取函数
retry_pull() {
    local max_retries=3
    local retry_count=0
    
    while [ $retry_count -lt $max_retries ]; do
        echo -e "${Green} [INFO] 尝试拉取项目更新 (第$((retry_count + 1))次)... ${Plain}"
        
        if git pull --no-tags origin master; then
            echo -e "${Green} [INFO] 项目更新成功！ ${Plain}"
            return 0
        else
            echo -e "${Red} [WARN] 拉取失败，5秒后重试... ${Plain}"
            retry_count=$((retry_count + 1))
            sleep 5
            
            # 如果重试失败，尝试切换镜像源
            if [ $retry_count -eq 1 ] && [ "${MIRRORS}" = "1" ]; then
                echo -e "${Yellow} [INFO] GHProxy失败，尝试切换到FastGIT... ${Plain}"
                git remote set-url origin https://hub.fastgit.xyz/Liu-cloud136/fans-medal-helper.git
            elif [ $retry_count -eq 2 ] && [ "${MIRRORS}" = "1" ]; then
                echo -e "${Yellow} [INFO] FastGIT失败，尝试切换到GitHub源... ${Plain}"
                git remote set-url origin https://github.com/Liu-cloud136/fans-medal-helper.git
            fi
        fi
    done
    
    echo -e "${Red} [ERR] 拉取失败，但继续运行本地代码... ${Plain}"
    return 1
}

echo -e "${Green} [INFO] 配置Git安全目录... ${Plain}"
git config --global --add safe.directory "*"

# 执行拉取
retry_pull

echo -e "${Green} [INFO] 开始运行... ${Plain}"
python3 main.py