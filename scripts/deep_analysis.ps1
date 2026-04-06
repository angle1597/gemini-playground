# A股深度分析脚本
# 对选出的股票进行全面深度分析

param(
    [string]$Code,
    [string]$Name
)

$ErrorActionPreference = "Continue"

# 配置
$CONFIG = @{
    SiliconFlowKey = 'sk-kpgfoaaozoiatwetyysvxzazmfnhzyypbynofxeapkzepgnv'
    ZhipuKey = 'b7ada653d37438954a8dafde78f66d7f.wY1fVXJkcsCiYJJi'
}

function Log($msg) {
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] $msg"
}

# 获取K线数据
function Get-KLineData($code, $days = 250) {
    $market = if ($code -like '6*') { 1 } else { 0 }
    $url = "https://push2his.eastmoney.com/api/qt/stock/kline/get?cb=&secid=$market.$code&ut=fa5fd1943c734e9f7ad383c97b4f4c5d&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61&klt=101&fqt=1&end=20500101&lmt=$days"
    try {
        $resp = Invoke-RestMethod -Uri $url -TimeoutSec 15
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
                    Amount = [double]$p[6]
                    Pct = [double]$p[7]
                }
            }
        }
    } catch {}
    return @()
}

# 计算技术指标
function Get-TechnicalIndicators($klines) {
    if ($klines.Count -lt 60) { return $null }
    
    $closes = $klines | ForEach-Object { $_.Close }
    $vols = $klines | ForEach-Object { $_.Vol }
    $highs = $klines | ForEach-Object { $_.High }
    $lows = $klines | ForEach-Object { $_.Low }
    
    # 均线
    $ma5 = ($closes | Select-Object -Last 5 | Measure-Object -Average).Average
    $ma10 = ($closes | Select-Object -Last 10 | Measure-Object -Average).Average
    $ma20 = ($closes | Select-Object -Last 20 | Measure-Object -Average).Average
    $ma60 = ($closes | Select-Object -Last 60 | Measure-Object -Average).Average
    
    # MACD
    $ema12 = $closes[0]
    $ema26 = $closes[0]
    $dif = @()
    for ($i = 1; $i -lt $closes.Count; $i++) {
        $ema12 = $closes[$i] * 0.1538 + $ema12 * 0.8462
        $ema26 = $closes[$i] * 0.0741 + $ema26 * 0.9259
        $dif += $ema12 - $ema26
    }
    $dea = $dif[0]
    for ($i = 1; $i -lt $dif.Count; $i++) {
        $dea = $dif[$i] * 0.2 + $dea * 0.8
    }
    $macd = ($dif[-1] - $dea) * 2
    
    # RSI
    $changes = @()
    for ($i = 1; $i -lt $closes.Count; $i++) {
        $changes += $closes[$i] - $closes[$i-1]
    }
    $last14 = $changes | Select-Object -Last 14
    $up = ($last14 | Where-Object { $_ -gt 0 } | Measure-Object -Sum).Sum
    $down = -($last14 | Where-Object { $_ -lt 0 } | Measure-Object -Sum).Sum
    $rsi = 100 - 100 / (1 + $up / ($down + 0.001))
    
    # KDJ
    $low9 = $lows | Select-Object -Last 9 | Measure-Object -Minimum
    $high9 = $highs | Select-Object -Last 9 | Measure-Object -Maximum
    $rsv = ($closes[-1] - $low9.Minimum) / ($high9.Maximum - $low9.Minimum + 0.001) * 100
    $k = $rsv
    $d = $rsv
    $j = 3 * $k - 2 * $d
    
    # 布林带
    $std20 = [Math]::Sqrt(($closes | Select-Object -Last 20 | ForEach-Object { [Math]::Pow($_ - $ma20, 2) } | Measure-Object -Average).Average)
    $upper = $ma20 + 2 * $std20
    $lower = $ma20 - 2 * $std20
    
    # 量比
    $volRatio = $vols[-1] / (($vols | Select-Object -Last 20 -Skip 1 | Measure-Object -Average).Average + 0.001)
    
    # 涨跌幅
    $change5d = ($closes[-1] - $closes[-5]) / $closes[-5] * 100
    $change10d = ($closes[-1] - $closes[-10]) / $closes[-10] * 100
    $change20d = ($closes[-1] - $closes[-20]) / $closes[-20] * 100
    $change60d = ($closes[-1] - $closes[-60]) / $closes[-60] * 100
    
    # 波动率
    $pcts = $klines | ForEach-Object { $_.Pct }
    $volatility = [Math]::Sqrt(($pcts | Select-Object -Last 20 | ForEach-Object { [Math]::Pow($_, 2) } | Measure-Object -Average).Average)
    
    return [PSCustomObject]@{
        MA5 = [Math]::Round($ma5, 2)
        MA10 = [Math]::Round($ma10, 2)
        MA20 = [Math]::Round($ma20, 2)
        MA60 = [Math]::Round($ma60, 2)
        MACD = [Math]::Round($macd, 4)
        DIF = [Math]::Round($dif[-1], 4)
        DEA = [Math]::Round($dea, 4)
        RSI = [Math]::Round($rsi, 1)
        K = [Math]::Round($k, 1)
        D = [Math]::Round($d, 1)
        J = [Math]::Round($j, 1)
        Upper = [Math]::Round($upper, 2)
        Lower = [Math]::Round($lower, 2)
        VolRatio = [Math]::Round($volRatio, 2)
        Change5d = [Math]::Round($change5d, 2)
        Change10d = [Math]::Round($change10d, 2)
        Change20d = [Math]::Round($change20d, 2)
        Change60d = [Math]::Round($change60d, 2)
        Volatility = [Math]::Round($volatility, 2)
    }
}

# LLM深度分析
function Get-LLMAnalysis($stock, $indicators) {
    $prompt = @"
你是一位资深A股分析师，请对以下股票进行深度分析：

## 基本信息
- 代码: $($stock.Code)
- 名称: $($stock.Name)
- 现价: $($stock.Price)元
- 市值: $($stock.MV)亿

## 技术指标
- 均线: MA5=$($indicators.MA5), MA10=$($indicators.MA10), MA20=$($indicators.MA20), MA60=$($indicators.MA60)
- MACD: MACD=$($indicators.MACD), DIF=$($indicators.DIF), DEA=$($indicators.DEA)
- RSI: $($indicators.RSI)
- KDJ: K=$($indicators.K), D=$($indicators.D), J=$($indicators.J)
- 布林带: 上轨=$($indicators.Upper), 下轨=$($indicators.Lower)
- 量比: $($indicators.VolRatio)
- 涨跌幅: 5日=$($indicators.Change5d)%, 10日=$($indicators.Change10d)%, 20日=$($indicators.Change20d)%, 60日=$($indicators.Change60d)%
- 波动率: $($indicators.Volatility)%

请分析：
1. 技术形态判断 (多头/空头/震荡)
2. 支撑位和压力位
3. 主力行为分析
4. 风险点
5. 未来一周走势预测
6. 综合评分 (1-10分)

请简洁回答，每项不超过50字。
"@

    try {
        $body = @{
            model = 'Qwen/Qwen2.5-72B-Instruct'
            messages = @(@{role='user'; content=$prompt})
            max_tokens = 500
        } | ConvertTo-Json -Depth 3
        
        $result = Invoke-RestMethod -Uri 'https://api.siliconflow.cn/v1/chat/completions' -Method POST -Headers @{ Authorization = "Bearer $($CONFIG.SiliconFlowKey)"; 'Content-Type' = 'application/json' } -Body $body -TimeoutSec 60
        return $result.choices[0].message.content
    } catch {
        return "LLM分析失败"
    }
}

# 主函数
function Start-DeepAnalysis {
    Log "=" * 60
    Log "A股深度分析系统"
    Log "=" * 60
    
    # 分析目标股票
    $targets = @(
        @{ Code = '002678'; Name = '珠江钢琴'; Price = 6.07; MV = 82.45 }
        @{ Code = '603585'; Name = '苏利股份'; Price = 24.51; MV = 45.81 }
        @{ Code = '000950'; Name = '重药控股'; Price = 7.14; MV = 123.39 }
    )
    
    $results = @()
    
    foreach ($stock in $targets) {
        Log ""
        Log "分析 $($stock.Code) $($stock.Name)..."
        Log "-" * 40
        
        # 1. 获取K线数据
        Log "[1/3] 获取K线数据..."
        $klines = Get-KLineData $stock.Code 250
        Log "   获取 $($klines.Count) 天数据"
        
        # 2. 计算技术指标
        Log "[2/3] 计算技术指标..."
        $indicators = Get-TechnicalIndicators $klines
        
        if ($indicators) {
            Log "   MA5=$($indicators.MA5) MA10=$($indicators.MA10) MA20=$($indicators.MA20)"
            Log "   RSI=$($indicators.RSI) K=$($indicators.K) D=$($indicators.D)"
            Log "   量比=$($indicators.VolRatio) 波动率=$($indicators.Volatility)%"
        }
        
        # 3. LLM深度分析
        Log "[3/3] LLM深度分析..."
        $llmResult = Get-LLMAnalysis $stock $indicators
        Log "   分析完成"
        
        $results += [PSCustomObject]@{
            Code = $stock.Code
            Name = $stock.Name
            Price = $stock.Price
            MV = $stock.MV
            Indicators = $indicators
            LLMAnalysis = $llmResult
        }
    }
    
    # 输出结果
    Log ""
    Log "=" * 60
    Log "深度分析报告"
    Log "=" * 60
    
    foreach ($r in $results) {
        Log ""
        Log "【$($r.Code) $($r.Name)】"
        Log "   现价: $($r.Price)元 | 市值: $($r.MV)亿"
        Log ""
        Log "   技术指标:"
        if ($r.Indicators) {
            Log "   - 均线: MA5=$($r.Indicators.MA5) MA10=$($r.Indicators.MA10) MA20=$($r.Indicators.MA20)"
            Log "   - MACD: $($r.Indicators.MACD) | RSI: $($r.Indicators.RSI)"
            Log "   - 量比: $($r.Indicators.VolRatio) | 波动率: $($r.Indicators.Volatility)%"
        }
        Log ""
        Log "   AI分析:"
        Log "   $($r.LLMAnalysis)"
    }
    
    # 保存结果
    $date = Get-Date -Format "yyyyMMdd_HHmmss"
    $output = @{
        timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        results = $results
    }
    $output | ConvertTo-Json -Depth 5 | Out-File "deep_analysis_$date.json" -Encoding UTF8
    Log ""
    Log "结果已保存: deep_analysis_$date.json"
}

Start-DeepAnalysis
