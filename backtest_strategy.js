/**
 * 选股策略回测验证
 * 验证策略历史表现
 */

const https = require('https');
const fs = require('fs');

// 配置
const CONFIG = {
    lookbackDays: 90,
    holdDays: 7,
    targetReturn: 0.30
};

// HTTP GET
const httpGet = (url) => new Promise((resolve, reject) => {
    https.get(url, { headers: { 'User-Agent': 'Mozilla/5.0' } }, (res) => {
        let data = '';
        res.on('data', (chunk) => data += chunk);
        res.on('end', () => resolve(data));
    }).on('error', reject);
});

// 获取K线
async function getKLine(code, days = 120) {
    const market = code.startsWith('6') ? 1 : 0;
    const url = `https://push2his.eastmoney.com/api/qt/stock/kline/get?cb=&secid=${market}.${code}&ut=fa5fd1943c734e9f7ad383c97b4f4c5d&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61&klt=101&fqt=1&end=20500101&lmt=${days}`;
    
    try {
        const data = await httpGet(url);
        const json = JSON.parse(data);
        if (json.data?.klines) {
            return json.data.klines.map(line => {
                const [date, open, close, high, low, vol, amount, pct] = line.split(',');
                return { date, open: +open, close: +close, high: +high, low: +low, vol: +vol, pct: +pct };
            });
        }
    } catch (e) {}
    return [];
}

// 计算评分
function calcScore(klines) {
    if (klines.length < 20) return { score: 0, signals: [] };
    
    const closes = klines.map(k => k.close);
    const vols = klines.map(k => k.vol);
    
    let score = 0;
    const signals = [];
    
    // 均线多头
    const ma5 = closes.slice(-5).reduce((a, b) => a + b, 0) / 5;
    const ma10 = closes.slice(-10).reduce((a, b) => a + b, 0) / 10;
    const ma20 = closes.slice(-20).reduce((a, b) => a + b, 0) / 20;
    
    if (ma5 > ma10 && ma10 > ma20) {
        score += 20;
        signals.push('均线多头');
    }
    
    // 放量
    const volRatio = vols[vols.length - 1] / (vols.slice(-20, -1).reduce((a, b) => a + b, 0) / 19);
    if (volRatio > 1.5) {
        score += 15;
        signals.push(`放量${volRatio.toFixed(1)}倍`);
    }
    
    // 涨幅
    const change10d = (closes[closes.length - 1] - closes[closes.length - 10]) / closes[closes.length - 10] * 100;
    if (change10d > 10) {
        score += 10;
        signals.push(`10日涨${change10d.toFixed(1)}%`);
    }
    
    return { score, signals };
}

// 回测
async function backtest() {
    console.log('='.repeat(60));
    console.log('选股策略回测验证');
    console.log(`回测周期: 最近${CONFIG.lookbackDays}天`);
    console.log(`持有周期: ${CONFIG.holdDays}天`);
    console.log(`目标收益: ${CONFIG.targetReturn * 100}%`);
    console.log('='.repeat(60));
    
    const testStocks = [
        { code: '603585', name: '苏利股份' },
        { code: '000950', name: '重药控股' },
        { code: '002678', name: '珠江钢琴' },
    ];
    
    const results = [];
    
    for (const stock of testStocks) {
        console.log(`\n回测 ${stock.code} ${stock.name}...`);
        
        const klines = await getKLine(stock.code, CONFIG.lookbackDays + 30);
        if (klines.length === 0) {
            console.log('  无法获取数据');
            continue;
        }
        
        const trades = [];
        
        for (let i = 30; i < klines.length - CONFIG.holdDays; i += CONFIG.holdDays) {
            const histKlines = klines.slice(i - 30, i);
            const { score, signals } = calcScore(histKlines);
            
            if (score >= 30) {
                const buyDate = klines[i].date;
                const buyPrice = klines[i].close;
                const sellDate = klines[i + CONFIG.holdDays].date;
                const sellPrice = klines[i + CONFIG.holdDays].close;
                const returns = (sellPrice - buyPrice) / buyPrice;
                
                trades.push({
                    buyDate, buyPrice, sellDate, sellPrice,
                    returns: returns * 100,
                    score, signals
                });
            }
        }
        
        if (trades.length > 0) {
            const winTrades = trades.filter(t => t.returns > 0);
            const highReturnTrades = trades.filter(t => t.returns >= CONFIG.targetReturn * 100);
            
            const winRate = winTrades.length / trades.length * 100;
            const highReturnRate = highReturnTrades.length / trades.length * 100;
            const avgReturn = trades.reduce((a, t) => a + t.returns, 0) / trades.length;
            const maxReturn = Math.max(...trades.map(t => t.returns));
            const minReturn = Math.min(...trades.map(t => t.returns));
            
            results.push({
                code: stock.code,
                name: stock.name,
                totalTrades: trades.length,
                winTrades: winTrades.length,
                winRate: winRate.toFixed(1),
                highReturnTrades: highReturnTrades.length,
                highReturnRate: highReturnRate.toFixed(1),
                avgReturn: avgReturn.toFixed(2),
                maxReturn: maxReturn.toFixed(2),
                minReturn: minReturn.toFixed(2)
            });
            
            console.log(`  交易次数: ${trades.length}`);
            console.log(`  胜率: ${winRate.toFixed(1)}%`);
            console.log(`  达标率(涨30%+): ${highReturnRate.toFixed(1)}%`);
            console.log(`  平均收益: ${avgReturn.toFixed(2)}%`);
            console.log(`  最大收益: ${maxReturn.toFixed(2)}%`);
            console.log(`  最大亏损: ${minReturn.toFixed(2)}%`);
        } else {
            console.log('  无符合条件的交易');
        }
    }
    
    // 汇总
    console.log('\n' + '='.repeat(60));
    console.log('回测汇总');
    console.log('='.repeat(60));
    
    if (results.length > 0) {
        const totalTrades = results.reduce((a, r) => a + r.totalTrades, 0);
        const totalWins = results.reduce((a, r) => a + r.winTrades, 0);
        const avgWinRate = results.reduce((a, r) => a + parseFloat(r.winRate), 0) / results.length;
        const avgHighReturnRate = results.reduce((a, r) => a + parseFloat(r.highReturnRate), 0) / results.length;
        const avgReturn = results.reduce((a, r) => a + parseFloat(r.avgReturn), 0) / results.length;
        
        console.log(`\n总交易次数: ${totalTrades}`);
        console.log(`总盈利次数: ${totalWins}`);
        console.log(`平均胜率: ${avgWinRate.toFixed(1)}%`);
        console.log(`平均达标率(涨30%+): ${avgHighReturnRate.toFixed(1)}%`);
        console.log(`平均收益: ${avgReturn.toFixed(2)}%`);
        
        // 保存
        const output = {
            timestamp: new Date().toISOString(),
            summary: {
                totalTrades,
                totalWins,
                avgWinRate: avgWinRate.toFixed(1),
                avgHighReturnRate: avgHighReturnRate.toFixed(1),
                avgReturn: avgReturn.toFixed(2)
            },
            details: results
        };
        
        fs.writeFileSync('backtest_result.json', JSON.stringify(output, null, 2));
        console.log('\n结果已保存: backtest_result.json');
        
        // 评估
        console.log('\n' + '='.repeat(60));
        if (avgHighReturnRate >= 30) {
            console.log('✅ 策略评估: 优秀 - 达标率超过30%');
        } else if (avgHighReturnRate >= 20) {
            console.log('⚠️ 策略评估: 良好 - 达标率20-30%');
        } else {
            console.log('❌ 策略评估: 需优化 - 达标率低于20%');
        }
        console.log('='.repeat(60));
    }
}

backtest().catch(console.error);
