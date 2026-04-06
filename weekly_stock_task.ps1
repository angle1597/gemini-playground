# A股选股定时任务脚本
# 每周日 20:00 执行

$ErrorActionPreference = "Continue"
$LogFile = "C:\Users\Administrator\.qclaw\logs\stock_pick.log"

function Log($msg) {
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$timestamp] $msg"
    Write-Host $line
    Add-Content -Path $LogFile -Value $line -ErrorAction SilentlyContinue
}

Log "=" * 60
Log "A股选股任务开始"
Log "=" * 60

try {
    # 1. 数据采集
    Log "[1/3] 数据采集..."
    $headers = @{ 'User-Agent' = 'Mozilla/5.0' }
    $url = 'https://push2.eastmoney.com/api/qt/clist/get?cb=&pn=1&pz=3000&po=1&np=1&ut=bd1d9ddb04089700511f6f89d92991d5&fltt=2&invt=2&fid=f3&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23&fields=f12,f14,f2,f3,f20'
    $response = Invoke-RestMethod -Uri $url -Headers $headers -TimeoutSec 30
    $stocks = @()
    
    foreach ($s in $response.data.diff) {
        $code = $s.f12
        $name = $s.f14
        $price = $s.f2
        $mv = $s.f20 / 100000000
        
        if ($name -match 'ST|退|\*') { continue }
        if ($code -like '300*' -or $code -like '688*' -or $code -like '8*' -or $code -like '4*') { continue }
        if ($price -ge 30 -or $price -le 0) { continue }
        if ($mv -lt 30 -or $mv -gt 150) { continue }
        
        $stocks += [PSCustomObject]@{ Code=$code; Name=$name; Price=$price; MV=[Math]::Round($mv,2) }
    }
    
    Log "筛选后股票数量: $($stocks.Count)"
    
    # 2. 技术分析
    Log "[2/3] 技术分析..."
    $results = @()
    
    foreach ($s in $stocks | Select-Object -First 50) {
        $market = if ($s.Code -like '6*') { 1 } else { 0 }
        $klineUrl = "https://push2his.eastmoney.com/api/qt/stock/kline/get?cb=&secid=$market.$($s.Code)&ut=fa5fd1943c734e9f7ad383c97b4f4c5d&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61&klt=101&fqt=1&end=20500101&lmt=30"
        
        try {
            $kdata = Invoke-RestMethod -Uri $klineUrl -TimeoutSec 5
            if ($kdata.data.klines) {
                $klines = $kdata.data.klines
                $last = $klines[-1] -split ','
                $first = $klines[0] -split ','
                $monthChange = [Math]::Round((($last[2] - $first[2]) / $first[2]) * 100, 2)
                $volToday = [double]$last[5]
                $vols = $klines | ForEach-Object { ($_ -split ',')[5] }
                $volAvg = ($vols | Select-Object -Last 20 | Measure-Object -Average).Average
                $volRatio = [Math]::Round($volToday / $volAvg, 2)
                
                $score = 0
                $signals = @()
                if ($monthChange -gt 10) { $score += 20; $signals += "月涨$monthChange%" }
                if ($volRatio -gt 1.5) { $score += 15; $signals += "放量$volRatio倍" }
                if ($last[7] -gt 5) { $score += 10; $signals += "今日涨$($last[7])%" }
                
                if ($score -ge 20) {
                    $results += [PSCustomObject]@{
                        Code=$s.Code
                        Name=$s.Name
                        Price=$s.Price
                        MV=$s.MV
                        Score=$score
                        Signals=$signals -join ', '
                    }
                }
            }
        } catch { }
    }
    
    $results = $results | Sort-Object Score -Descending
    Log "筛选出潜力股: $($results.Count)"
    
    # 3. LLM分析 (使用硅基流动免费API)
    Log "[3/3] LLM深度分析..."
    $top3 = $results | Select-Object -First 3
    
    foreach ($r in $top3) {
        $prompt = "Analyze A-share stock: Code $($r.Code) $($r.Name), Price $($r.Price) CNY, Market Cap $($r.MV)B CNY, Score $($r.Score). Give trend, support/resistance, 1-week prediction, risk level. Be concise."
        
        $body = @{
            model = 'Qwen/Qwen2.5-72B-Instruct'
            messages = @(@{role='user'; content=$prompt})
            max_tokens = 200
        } | ConvertTo-Json -Depth 3
        
        try {
            $llmResult = Invoke-RestMethod -Uri 'https://api.siliconflow.cn/v1/chat/completions' -Method POST -Headers @{ Authorization='Bearer sk-kpgfoaaozoiatwetyysvxzazmfnhzyypbynofxeapkzepgnv'; 'Content-Type'='application/json' } -Body $body -TimeoutSec 30
            $r | Add-Member -NotePropertyName "LLMAnalysis" -NotePropertyValue $llmResult.choices[0].message.content
            Log "分析 $($r.Name): $($llmResult.choices[0].message.content.Substring(0, [Math]::Min(50, $llmResult.choices[0].message.content.Length)))..."
        } catch {
            Log "分析 $($r.Name): LLM调用失败"
        }
    }
    
    # 输出结果
    Log ""
    Log "=" * 60
    Log "本周精选股票 (Top 3)"
    Log "=" * 60
    
    for ($i = 0; $i -lt $top3.Count; $i++) {
        $s = $top3[$i]
        Log "$($i+1). $($s.Code) $($s.Name)"
        Log "   现价: $($s.Price)元 | 市值: $($s.MV)亿"
        Log "   评分: $($s.Score)分 | 信号: $($s.Signals)"
        if ($s.LLMAnalysis) {
            Log "   LLM: $($s.LLMAnalysis.Substring(0, [Math]::Min(80, $s.LLMAnalysis.Length)))..."
        }
    }
    
    # 保存结果
    $output = @{
        timestamp = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
        top_stocks = $top3
    }
    
    $outputFile = "C:\Users\Administrator\.qclaw\workspace\weekly_pick_$(Get-Date -Format 'yyyyMMdd').json"
    $output | ConvertTo-Json -Depth 5 | Out-File -FilePath $outputFile -Encoding UTF8
    Log "结果已保存: $outputFile"
    
    Log ""
    Log "=" * 60
    Log "任务完成"
    Log "=" * 60
    
} catch {
    Log "错误: $_"
}
