# A股最终选股脚本 - 多金叉共振 + 大盘过滤
# 每15分钟自动执行并汇报

param(
    [switch]$Report  # 是否发送汇报
)

$ErrorActionPreference = "Continue"

function Log($msg) {
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] $msg"
}

# 获取上证指数MA20方向
function Get-MarketTrend {
    $url = "https://push2his.eastmoney.com/api/qt/stock/kline/get?cb=&secid=1.000001&ut=fa5fd1943c734e9f7ad383c97b4f4c5d&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61&klt=101&fqt=1&end=20500101&lmt=30"
    try {
        $resp = Invoke-RestMethod -Uri $url -TimeoutSec 10
        $closes = $resp.data.klines | ForEach-Object { ($_ -split ',')[2] }
        $ma20 = ($closes | Select-Object -Last 20 | Measure-Object -Average).Average
        $ma20Prev = ($closes | Select-Object -Last 21 -Skip 1 | Measure-Object -Average).Average
        return $ma20 -gt $ma20Prev
    } catch {
        return $false
    }
}

# 获取股票列表
function Get-StockList {
    $url = 'https://push2.eastmoney.com/api/qt/clist/get?cb=&pn=1&pz=3000&po=1&np=1&ut=bd1d9ddb04089700511f6f89d92991d5&fltt=2&invt=2&fid=f3&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23&fields=f12,f14,f2,f3,f20'
    $headers = @{ 'User-Agent' = 'Mozilla/5.0' }
    try {
        $resp = Invoke-RestMethod -Uri $url -Headers $headers -TimeoutSec 30
        $stocks = @()
        foreach ($s in $resp.data.diff) {
            $code = $s.f12; $name = $s.f14; $price = $s.f2
            $mv = $s.f20 / 100000000
            if ($name -match 'ST|退|\*') { continue }
            if ($code -like '300*' -or $code -like '688*' -or $code -like '8*' -or $code -like '4*') { continue }
            if ($price -ge 30 -or $price -le 0) { continue }
            if ($mv -lt 30 -or $mv -gt 150) { continue }
            $stocks += [PSCustomObject]@{ Code=$code; Name=$name; Price=$price; MV=[Math]::Round($mv,2) }
        }
        return $stocks
    } catch {
        return @()
    }
}

# 分析股票
function Analyze-Stock($code, $klines) {
    if ($klines.Count -lt 50) { return $null }
    
    $c = $klines | ForEach-Object { $_.Close }
    $v = $klines | ForEach-Object { $_.Vol }
    
    $ma5 = ($c | Select-Object -Last 5 | Measure-Object -Average).Average
    $ma10 = ($c | Select-Object -Last 10 | Measure-Object -Average).Average
    $ma20 = ($c | Select-Object -Last 20 | Measure-Object -Average).Average
    
    $volRatio = $v[-1] / (($v | Select-Object -Last 20 -Skip 1 | Measure-Object -Average).Average + 0.001)
    
    $score = 0
    $signals = @()
    
    # 均线多头
    if ($ma5 -gt $ma10 -and $ma10 -gt $ma20) {
        $score += 40
        $signals += '均线多头'
    } elseif ($ma5 -gt $ma10) {
        $score += 20
        $signals += '短期向上'
    }
    
    # 放量
    if ($volRatio -gt 2) {
        $score += 30
        $signals += "放量$([Math]::Round($volRatio,1))倍"
    } elseif ($volRatio -gt 1.5) {
        $score += 20
        $signals += "放量$([Math]::Round($volRatio,1))倍"
    }
    
    # 涨幅
    $change = ($c[-1] - $c[-10]) / $c[-10] * 100
    if ($change -gt 5 -and $change -lt 20) {
        $score += 20
        $signals += "10日涨$([Math]::Round($change,1))%"
    }
    
    return @{ Score=$score; Signals=$signals }
}

# 主函数
function Main {
    Log "=" * 50
    Log "A股选股系统 - 最终策略"
    Log "=" * 50
    
    # 1. 检查大盘
    Log "[1/3] 检查大盘趋势..."
    $marketUp = Get-MarketTrend
    if (-not $marketUp) {
        Log "大盘趋势向下，暂停操作"
        return
    }
    Log "大盘趋势向上 ✅"
    
    # 2. 获取股票列表
    Log "[2/3] 获取股票列表..."
    $stocks = Get-StockList
    Log "筛选后: $($stocks.Count) 只股票"
    
    # 3. 分析股票
    Log "[3/3] 分析股票..."
    $results = @()
    
    foreach ($s in $stocks | Select-Object -First 50) {
        $market = if ($s.Code -like '6*') { 1 } else { 0 }
        $url = "https://push2his.eastmoney.com/api/qt/stock/kline/get?cb=&secid=$market.$($s.Code)&ut=fa5fd1943c734e9f7ad383c97b4f4c5d&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61&klt=101&fqt=1&end=20500101&lmt=60"
        try {
            $kdata = Invoke-RestMethod -Uri $url -TimeoutSec 5
            $klines = $kdata.data.klines | ForEach-Object {
                $p = $_ -split ','
                [PSCustomObject]@{ Close=[double]$p[2]; Vol=[double]$p[5] }
            }
            $analysis = Analyze-Stock $s.Code $klines
            if ($analysis -and $analysis.Score -ge 60) {
                $results += [PSCustomObject]@{
                    Code=$s.Code
                    Name=$s.Name
                    Price=$s.Price
                    MV=$s.MV
                    Score=$analysis.Score
                    Signals=$analysis.Signals -join ', '
                }
            }
        } catch {}
    }
    
    $results = $results | Sort-Object Score -Descending
    $top3 = $results | Select-Object -First 3
    
    # 输出结果
    Log ""
    Log "=" * 50
    Log "选股结果 (Top 3)"
    Log "=" * 50
    
    foreach ($r in $top3) {
        Log ""
        Log "$($r.Code) $($r.Name)"
        Log "  价格: $($r.Price) | 市值: $($r.MV)亿"
        Log "  评分: $($r.Score) | 信号: $($r.Signals)"
    }
    
    # 保存结果
    $date = Get-Date -Format "yyyyMMdd_HHmm"
    $output = @{
        timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        market_trend = "UP"
        results = $top3
    }
    $output | ConvertTo-Json -Depth 5 | Out-File "result_$date.json" -Encoding UTF8
    Log ""
    Log "结果已保存"
}

Main
