# .env 文件加载工具，被 start_prod.ps1 / start_public.ps1 共用。
#
# 规则：
# - 跳过空行 / 整行以 # 开头的注释
# - 行内 `#` 视作注释起点（前必须有空格，避免误伤 token 内的 #）
# - 两端可选双/单引号，长度<2 时不剥
# - 自动去 BOM 与 CR
#
# 调用：
#   . "$PSScriptRoot\scripts\Load-DotEnv.ps1"
#   Import-DotEnv -Path .\.env

function Import-DotEnv {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string] $Path
    )

    if (-not (Test-Path $Path)) {
        throw ".env 文件不存在：$Path"
    }

    Get-Content -LiteralPath $Path -Encoding UTF8 | ForEach-Object {
        # 去 BOM + CR
        $line = ($_ -replace "^﻿", '').TrimEnd("`r").Trim()
        if (-not $line -or $line.StartsWith('#')) { return }

        # 行内注释：仅当 # 前有空白时才剥（避免误剥 token 内 #）
        $hashIdx = -1
        $inSingle = $false
        $inDouble = $false
        for ($i = 0; $i -lt $line.Length; $i++) {
            $c = $line[$i]
            if ($c -eq "'" -and -not $inDouble) { $inSingle = -not $inSingle }
            elseif ($c -eq '"' -and -not $inSingle) { $inDouble = -not $inDouble }
            elseif ($c -eq '#' -and -not $inSingle -and -not $inDouble) {
                if ($i -eq 0 -or [char]::IsWhiteSpace($line[$i - 1])) { $hashIdx = $i; break }
            }
        }
        if ($hashIdx -ge 0) { $line = $line.Substring(0, $hashIdx).Trim() }

        $idx = $line.IndexOf('=')
        if ($idx -lt 1) { return }
        $key = $line.Substring(0, $idx).Trim()
        $val = $line.Substring($idx + 1).Trim()

        # 两端引号剥离（双引号或单引号，长度必须 >=2 且首尾匹配）
        if ($val.Length -ge 2) {
            $first = $val[0]; $last = $val[$val.Length - 1]
            if (($first -eq '"' -and $last -eq '"') -or ($first -eq "'" -and $last -eq "'")) {
                $val = $val.Substring(1, $val.Length - 2)
            }
        }

        # key 校验：只允许字母数字下划线
        if ($key -notmatch '^[A-Za-z_][A-Za-z0-9_]*$') { return }

        Set-Item -Path "Env:$key" -Value $val
    }
}

function Assert-EnvRequired {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string[]] $Keys,
        [string[]] $Placeholders = @(),
        # 标记为"密钥类"的 key 会做最小长度（24）校验；其它（如 bool flag）跳过
        [string[]] $SecretKeys = @()
    )
    foreach ($k in $Keys) {
        $v = (Get-Item -Path "Env:$k" -ErrorAction SilentlyContinue).Value
        if (-not $v) { throw "$k 未在 .env 中配置" }
        foreach ($p in $Placeholders) {
            if ($v -eq $p) { throw "$k 仍为占位符 '$p'，请用真实值替换" }
        }
        if (($k -in $SecretKeys) -and ($v.Length -lt 24)) {
            # 公网部署密钥强度过低，直接 fail-fast；避免弱 token 启动后被暴力穷举。
            # 错误消息不打印实际长度（精确长度对攻击者是有用情报，能缩小爆破空间）。
            throw "$k 不满足最小长度（24 字符）。生成强随机：python -c ""import secrets; print(secrets.token_urlsafe(32))"""
        }
    }
}
