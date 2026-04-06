# A股选股策略回测系统
# 用历史数据验证策略有效性

param(
    [int]$Years = 5,  # 回测年数
    [int]$MinScore = 25
)

$ErrorActionPreference = "Continue"

function Log($msg) {
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] $msg"
}

# 获取历史K线
function Get-HistoryKLine($code, $years = 5) {
    $market = if ($code -like '6*') { 1 } else { 0 }
    $days = $years * 250
    $url = "https://push2his.eastmoney.com/api/qt/stock/kline/get?cb=&secid=$market.$code&ut=fa5fd1943c734e9f7ad383c97b4f4c5d&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61&klt=101&fqt=1&end=20500101&lmt=$days"
    try {
        $resp = Invoke-RestMethod -Uri $url -TimeoutSec 30
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

# 选股策略评分
function Get-StrategyScore($klines, $index) {
    if ($index -lt 60) { return 0 }
    
    # 取当前窗口的数据
    $window = $klines[($index - 60)..$index]
    $closes = $window | ForEach-Object { $_.Close }
    $vols = $window | ForEach-Object { $_.Vol }
    
    $score = 0
    
    # 策略1: 均线多头排列 (MA5 > MA10 > MA20)
    $ma5 = ($closes | Select-Object -Last 5 | Measure-Object -Average).Average
    $ma10 = ($closes | Select-Object -Last 10 | Measure-Object -Average).Average
    $ma20 = ($closes | Select-Object -Last 20 | Measure-Object -Average).Average
    if ($ma5 -gt $ma10 -and $ma10 -gt $ma20) { $score += 20 }
    elseif ($ma5 -gt $ma10) { $score += 10 }
    
    # 策略2: 放量突破
    $volToday = $vols[-1]
    $volAvg = ($vols | Select-Object -Last 20 -Skip 1 | Measure-Object -Average).Average
    $volRatio = $volToday / ($volAvg + 0.001)
    if ($volRatio -gt 2) { $score += 20 }
    elseif ($volRatio -gt 1.5) { $score += 15 }
    elseif ($volRatio -gt 1.2) { $score += 10 }
    
    # 策略3: 近期涨幅
    $change10d = ($closes[-1] - $closes[-10]) / $closes[-10] * 100
    if ($change10d -gt 15 -and $change10d -lt 30) { $score += 20 }
    elseif ($change10d -gt 10 -and $change10d -lt 25) { $score += 15 }
    elseif ($change10d -gt 5) { $score += 10 }
    
    # 策略4: 突破20日高点
    $high20 = ($window | Select-Object -Last 20 -Skip 1 | ForEach-Object { $_.High } | Measure-Object -Maximum).Maximum
    if ($closes[-1] -gt $high20) { $score += 15 }
    
    # 策略5: RSI不超买
    $changes = @()
    for ($i = 1; $i -lt $closes.Count; $i++) {
        $changes += $closes[$i] - $closes[$i-1]
    }
    $last14 = $changes | Select-Object -Last 14
    $up = ($last14 | Where-Object { $_ -gt 0 } | Measure-Object -Sum).Sum
    $down = -($last14 | Where-Object { $_ -lt 0 } | Measure-Object -Sum).Sum
    $rsi = 100 - 100 / (1 + $up / ($down + 0.001))
    if ($rsi -lt 70 -and $rsi -gt 30) { $score += 10 }
    if ($rsi -lt 60 -and $rsi -gt 40) { $score += 5 }
    
    return $score
}

# 回测单只股票
function Backtest-Stock($code, $name, $years = 5) {
    Log "回测 $code $name..."
    
    $klines = Get-HistoryKLine $code $years
    if ($klines.Count -lt 250) {
        Log "  数据不足: $($klines.Count) 天"
        return $null
    }
    
    Log "  获取 $($klines.Count) 天历史数据"
    
    $trades = @()
    $holdDays = 7  # 持有周期
    $targetReturn = 30  # 目标收益30%
    
    # 遍历历史数据，模拟交易
    for ($i = 60; $i -lt $klines.Count - $holdDays; $i++) {
        $score = Get-StrategyScore $klines $i
        
        if ($score -ge $MinScore) {
            # 买入信号
            $buyPrice = $klines[$i].Close
            $buyDate = $klines[$i].Date
            
            # 持有holdDays天后卖出
            $sellPrice = $klines[$i + $holdDays].Close
            $sellDate = $klines[$i + $holdDays].Date
            $return = ($sellPrice - $buyPrice) / $buyPrice * 100
            
            $trades += [PSCustomObject]@{
                BuyDate = $buyDate
                BuyPrice = [Math]::Round($buyPrice, 2)
                SellDate = $sellDate
                SellPrice = [Math]::Round($sellPrice, 2)
                Return = [Math]::Round($return, 2)
                Score = $score
                Success = $return -gt 0
                TargetHit = $return -ge $targetReturn
            }
        }
    }
    
    if ($trades.Count -eq 0) {
        Log "  无交易信号"
        return $null
    }
    
    # 统计结果
    $winCount = ($trades | Where-Object { $_.Success }).Count
    $targetCount = ($trades | Where-Object { $_.TargetHit }).Count
    $avgReturn = ($trades | Measure-Object -Property Return -Average).Average
    $maxReturn = ($trades | Measure-Object -Property Return -Maximum).Maximum
    $minReturn = ($trades | Measure-Object -Property Return -Minimum).Minimum
    
    $result = [PSCustomObject]@{
        Code = $code
        Name = $name
        TotalTrades = $trades.Count
        WinCount = $winCount
        WinRate = [Math]::Round($winCount / $trades.Count * 100, 1)
        TargetCount = $targetCount
        TargetRate = [Math]::Round($targetCount / $trades.Count * 100, 1)
        AvgReturn = [Math]::Round($avgReturn, 2)
        MaxReturn = [Math]::Round($maxReturn, 2)
        MinReturn = [Math]::Round($minReturn, 2)
        Trades = $trades
    }
    
    Log "  交易次数: $($trades.Count)"
    Log "  胜率: $($result.WinRate)%"
    Log "  达标率(30%+): $($result.TargetRate)%"
    Log "  平均收益: $($result.AvgReturn)%"
    
    return $result
}

# 主函数
function Main {
    Log "=" * 60
    Log "A股选股策略回测系统"
    Log "回测周期: $Years 年"
    Log "最低评分: $MinScore"
    Log "=" * 60
    
    # 回测股票列表 (有代表性的股票)
    $testStocks = @(
        @{ Code = '002678'; Name = 'Zhujiang Piano' }
        @{ Code = '603585'; Name = 'Suli' }
        @{ Code = '000950'; Name = 'Chongyao' }
        @{ Code = '600488'; Name = 'Jinyao' }
        @{ Code = '603122'; Name = 'Hefu' }
        @{ Code = '000001'; Name = 'PingAn' }
        @{ Code = '600036'; Name = 'ZhaoShang' }
        @{ Code = '000858'; Name = 'Wuliangye' }
    )
    
    $results = @()
    
    foreach ($stock in $testStocks) {
        $result = Backtest-Stock $stock.Code $stock.Name $Years
        if ($result) {
            $results += $result
        }
        Log ""
    }
    
    # 汇总结果
    Log "=" * 60
    Log "回测汇总"
    Log "=" * 60
    
    if ($results.Count -gt 0) {
        $totalTrades = ($results | Measure-Object -Property TotalTrades -Sum).Sum
        $totalWins = ($results | Measure-Object -Property WinCount -Sum).Sum
        $totalTargets = ($results | Measure-Object -Property TargetCount -Sum).Sum
        $avgWinRate = ($results | Measure-Object -Property WinRate -Average).Average
        $avgTargetRate = ($results | Measure-Object -Property TargetRate -Average).Average
        $avgReturn = ($results | Measure-Object -Property AvgReturn -Average).Average
        
        Log ""
        Log "总交易次数: $totalTrades"
        Log "总盈利次数: $totalWins"
        Log "平均胜率: $([Math]::Round($avgWinRate, 1))%"
        Log "平均达标率(30%+): $([Math]::Round($avgTargetRate, 1))%"
        Log "平均收益: $([Math]::Round($avgReturn, 2))%"
        Log ""
        
        # 策略评估
        Log "=" * 60
        Log "策略评估"
        Log "=" * 60
        
        if ($avgWinRate -ge 60) {
            Log "胜率: ✅ 良好 (>=60%)"
        } elseif ($avgWinRate -ge 50) {
            Log "胜率: ⚠️ 一般 (50-60%)"
        } else {
            Log "胜率: ❌ 不足 (<50%)"
        }
        
        if ($avgTargetRate -ge 20) {
            Log "达标率: ✅ 良好 (>=20%)"
        } elseif ($avgTargetRate -ge 10) {
            Log "达标率: ⚠️ 一般 (10-20%)"
        } else {
            Log "达标率: ❌ 不足 (<10%)"
        }
        
        if ($avgReturn -gt 0) {
            Log "平均收益: ✅ 正收益"
        } else {
            Log "平均收益: ❌ 负收益"
        }
        
        # 保存结果
        $date = Get-Date -Format "yyyyMMdd_HHmmss"
        $output = @{
            timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
            years = $Years
            minScore = $MinScore
            summary = @{
                totalTrades = $totalTrades
                totalWins = $totalWins
                avgWinRate = [Math]::Round($avgWinRate, 1)
                avgTargetRate = [Math]::Round($avgTargetRate, 1)
                avgReturn = [Math]::Round($avgReturn, 2)
            }
            results = $results | Select-Object -Property * -ExcludeProperty Trades
        }
        $output | ConvertTo-Json -Depth 5 | Out-File "backtest_result_$date.json" -Encoding UTF8
        Log ""
        Log "结果已保存: backtest_result_$date.json"
    }
}

Main
