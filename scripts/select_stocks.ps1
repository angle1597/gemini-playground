# A股每周选股脚本 - PowerShell版
# 用于GitHub Actions自动化执行

$ErrorActionPreference = "Continue"

# 配置
$CONFIG = @{
    MinMarketCap = 30
    MaxMarketCap = 150
    MaxPrice = 30
    TopN = 3
    MinScore = 25
}

# 日志函数
function Log($msg) {
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-Host "[$timestamp] $msg"
}

# 获取股票列表
function Get-StockList {
    Log "获取A股股票列表..."
    $url = 'https://push2.eastmoney.com/api/qt/clist/get?cb=&pn=1&pz=3000&po=1&np=1&ut=bd1d9ddb04089700511f6f89d92991d5&fltt=2&invt=2&fid=f3&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23&fields=f12,f14,f2,f3,f20'
    $headers = @{ 'User-Agent' = 'Mozilla/5.0' }
    
    try {
        $resp = Invoke-RestMethod -Uri $url -Headers $headers -TimeoutSec 30
        $stocks = @()
        
        foreach ($item in $resp.data.diff) {
            $code = $item.f12
            $name = $item.f14
            $price = $item.f2
            $mv = $item.f20 / 100000000
            
            # 过滤
            if ($name -match 'ST|退|\*') { continue }
            if ($code -like '300*' -or $code -like '688*') { continue }
            if ($code -like '8*' -or $code -like '4*') { continue }
            if ($price -ge $CONFIG.MaxPrice -or $price -le 0) { continue }
            if ($mv -lt $CONFIG.MinMarketCap -or $mv -gt $CONFIG.MaxMarketCap) { continue }
            
            $stocks += [PSCustomObject]@{
                Code = $code
                Name = $name
                Price = [Math]::Round($price, 2)
                MV = [Math]::Round($mv, 2)
                Change = $item.f3
            }
        }
        
        Log "筛选后: $($stocks.Count) 只股票"
        return $stocks
    } catch {
        Log "错误: $_"
        return @()
    }
}

# 获取K线
function Get-KLine($code, $days = 60) {
    $market = if ($code -like '6*') { 1 } else { 0 }
    $url = "https://push2his.eastmoney.com/api/qt/stock/kline/get?cb=&secid=$market.$code&ut=fa5fd1943c734e9f7ad383c97b4f4c5d&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61&klt=101&fqt=1&end=20500101&lmt=$days"
    
    try {
        $resp = Invoke-RestMethod -Uri $url -TimeoutSec 10
        if ($resp.data.klines) {
            return $resp.data.klines | ForEach-Object {
                $p = $_ -split ','
                [PSCustomObject]@{
                    Date = $p[0]
                    Open = [double]$p[1]
                    Close = [double]$p[2]
                    High = [double]$p[3]
                    Low = [double]$p[4]
                    Vol = [double]$p[5]
                    Pct = [double]$p[7]
                }
            }
        }
    } catch {}
    return @()
}

# 分析股票
function Analyze-Stock($klines) {
    if ($klines.Count -lt 20) { return @{ Score = 0; Signals = @() } }
    
    $closes = $klines | ForEach-Object { $_.Close }
    $vols = $klines | ForEach-Object { $_.Vol }
    
    $score = 0
    $signals = @()
    
    # 均线
    $ma5 = ($closes | Select-Object -Last 5 | Measure-Object -Average).Average
    $ma10 = ($closes | Select-Object -Last 10 | Measure-Object -Average).Average
    $ma20 = ($closes | Select-Object -Last 20 | Measure-Object -Average).Average
    
    if ($ma5 -gt $ma10 -and $ma10 -gt $ma20) {
        $score += 20
        $signals += '均线多头'
    } elseif ($ma5 -gt $ma10) {
        $score += 10
        $signals += '短期向上'
    }
    
    # 放量
    $lastVol = $vols[-1]
    $avgVol = ($vols | Select-Object -Last 20 -Skip 1 | Measure-Object -Average).Average
    $volRatio = $lastVol / ($avgVol + 0.001)
    
    if ($volRatio -gt 2) {
        $score += 20
        $signals += "放量$([Math]::Round($volRatio, 1))倍"
    } elseif ($volRatio -gt 1.5) {
        $score += 15
        $signals += "放量$([Math]::Round($volRatio, 1))倍"
    }
    
    # 涨幅
    $lastClose = $closes[-1]
    $close10 = $closes[-10]
    $change10d = ($lastClose - $close10) / $close10 * 100
    
    if ($change10d -gt 15) {
        $score += 15
        $signals += "10日涨$([Math]::Round($change10d, 1))%"
    } elseif ($change10d -gt 10) {
        $score += 10
        $signals += "10日涨$([Math]::Round($change10d, 1))%"
    }
    
    # 突破
    $recentHigh = ($klines | Select-Object -Last 20 -Skip 1 | ForEach-Object { $_.High } | Measure-Object -Maximum).Maximum
    if ($lastClose -gt $recentHigh) {
        $score += 15
        $signals += '突破20日高点'
    }
    
    return @{ Score = $score; Signals = $signals }
}

# 主函数
function Main {
    Log "=" * 60
    Log "A股每周选股系统"
    Log "=" * 60
    
    # 1. 获取股票列表
    Log "[1/2] 获取股票列表..."
    $stocks = Get-StockList
    
    if ($stocks.Count -eq 0) {
        Log "无符合条件的股票"
        return
    }
    
    # 2. 技术分析
    Log "[2/2] 技术分析..."
    $results = @()
    
    for ($i = 0; $i -lt $stocks.Count; $i++) {
        $stock = $stocks[$i]
        
        if (($i + 1) % 20 -eq 0) {
            Log "  进度: $($i + 1)/$($stocks.Count)"
        }
        
        $klines = Get-KLine $stock.Code 60
        if ($klines.Count -lt 20) { continue }
        
        $analysis = Analyze-Stock $klines
        if ($analysis.Score -ge $CONFIG.MinScore) {
            $results += [PSCustomObject]@{
                Code = $stock.Code
                Name = $stock.Name
                Price = $stock.Price
                MV = $stock.MV
                Score = $analysis.Score
                Signals = $analysis.Signals -join ', '
            }
        }
    }
    
    $results = $results | Sort-Object Score -Descending
    Log "  筛选出: $($results.Count) 只潜力股"
    
    # 输出结果
    $topStocks = $results | Select-Object -First $CONFIG.TopN
    
    Log ""
    Log "=" * 60
    Log "本周精选股票 (Top $($CONFIG.TopN))"
    Log "=" * 60
    
    for ($i = 0; $i -lt $topStocks.Count; $i++) {
        $s = $topStocks[$i]
        Log ""
        Log "$($i + 1). $($s.Code) $($s.Name)"
        Log "   现价: $($s.Price)元 | 市值: $($s.MV)亿"
        Log "   评分: $($s.Score)分 | 信号: $($s.Signals)"
    }
    
    # 保存结果
    $date = Get-Date -Format "yyyyMMdd"
    $output = @{
        timestamp = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
        top_stocks = $topStocks
    }
    
    $output | ConvertTo-Json -Depth 5 | Out-File "weekly_pick_$date.json" -Encoding UTF8
    Log ""
    Log "结果已保存: weekly_pick_$date.json"
    
    # GitHub Actions输出
    if ($env:GITHUB_OUTPUT) {
        $summary = ($topStocks | ForEach-Object { "$($_.Code) $($_.Name) - 现价$($_.Price)元, 评分$($_.Score)分" }) -join "`n"
        Add-Content -Path $env:GITHUB_OUTPUT -Value "result<<EOF`n$summary`nEOF"
    }
    
    Log ""
    Log "=" * 60
    Log "✅ 选股完成"
    Log "=" * 60
}

Main
