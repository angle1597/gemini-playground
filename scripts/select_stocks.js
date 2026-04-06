/**
 * A股选股核心脚本
 * 用于GitHub Actions自动化执行
 */

const https = require('https');
const http = require('http');
const fs = require('fs');

// 配置
const CONFIG = {
  minMarketCap: 30,
  maxMarketCap: 150,
  maxPrice: 30,
  topN: 3,
  minScore: 25  // 降低评分门槛，增加交易机会
};

// HTTP GET
const httpGet = (url) => new Promise((resolve, reject) => {
  const client = url.startsWith('https') ? https : http;
  const req = client.get(url, {
    headers: { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36' },
    timeout: 15000
  }, (res) => {
    let data = '';
    res.on('data', (chunk) => data += chunk);
    res.on('end', () => resolve(data));
  });
  req.on('error', reject);
  req.on('timeout', () => { req.destroy(); reject(new Error('Timeout')); });
});

// 获取股票列表
async function getStockList() {
  console.log('获取A股股票列表...');
  const url = 'https://push2.eastmoney.com/api/qt/clist/get?cb=&pn=1&pz=3000&po=1&np=1&ut=bd1d9ddb04089700511f6f89d92991d5&fltt=2&invt=2&fid=f3&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23&fields=f12,f14,f2,f3,f20';
  
  const data = await httpGet(url);
  const json = JSON.parse(data);
  
  const stocks = [];
  for (const item of json.data.diff) {
    const code = item.f12;
    const name = item.f14;
    const price = item.f2;
    const mv = item.f20 === '-' ? 0 : item.f20 / 100000000;
    
    // 过滤条件
    if (!name || name.includes('ST') || name.includes('退') || name.includes('*')) continue;
    if (code.startsWith('300')) continue;  // 创业板
    if (code.startsWith('688')) continue;  // 科创板
    if (code.startsWith('8') || code.startsWith('4')) continue;  // 北交所
    if (price <= 0 || price >= CONFIG.maxPrice) continue;
    if (mv < CONFIG.minMarketCap || mv > CONFIG.maxMarketCap) continue;
    
    stocks.push({
      code,
      name,
      price: Math.round(price * 100) / 100,
      mv: Math.round(mv * 100) / 100,
      change: item.f3
    });
  }
  
  console.log(`筛选后: ${stocks.length} 只股票`);
  return stocks;
}

// 获取K线
async function getKLine(code, days = 60) {
  const market = code.startsWith('6') ? 1 : 0;
  const url = `https://push2his.eastmoney.com/api/qt/stock/kline/get?cb=&secid=${market}.${code}&ut=fa5fd1943c734e9f7ad383c97b4f4c5d&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61&klt=101&fqt=1&end=20500101&lmt=${days}`;
  
  try {
    const data = await httpGet(url);
    const json = JSON.parse(data);
    if (json.data?.klines) {
      return json.data.klines.map(line => {
        const p = line.split(',');
        return {
          date: p[0],
          open: +p[1],
          close: +p[2],
          high: +p[3],
          low: +p[4],
          vol: +p[5],
          pct: +p[7]
        };
      });
    }
  } catch (e) {}
  return [];
}

// 计算技术指标和评分
function analyzeStock(klines) {
  if (klines.length < 20) return { score: 0, signals: [], indicators: {} };
  
  const closes = klines.map(k => k.close);
  const vols = klines.map(k => k.vol);
  const last = klines[klines.length - 1];
  
  let score = 0;
  const signals = [];
  
  // 均线
  const ma5 = closes.slice(-5).reduce((a, b) => a + b, 0) / 5;
  const ma10 = closes.slice(-10).reduce((a, b) => a + b, 0) / 10;
  const ma20 = closes.slice(-20).reduce((a, b) => a + b, 0) / 20;
  
  if (ma5 > ma10 && ma10 > ma20) {
    score += 20;
    signals.push('均线多头');
  } else if (ma5 > ma10) {
    score += 10;
    signals.push('短期向上');
  }
  
  // 股价站上均线
  const lastClose = closes[closes.length - 1];
  if (lastClose > ma5 && lastClose > ma10) {
    score += 10;
    signals.push('站上均线');
  }
  
  // 放量
  const volRatio = vols[vols.length - 1] / (vols.slice(-20, -1).reduce((a, b) => a + b, 0) / 19 + 0.001);
  if (volRatio > 2) {
    score += 20;
    signals.push(`放量${volRatio.toFixed(1)}倍`);
  } else if (volRatio > 1.5) {
    score += 15;
    signals.push(`放量${volRatio.toFixed(1)}倍`);
  } else if (volRatio > 1.2) {
    score += 8;
    signals.push('温和放量');
  }
  
  // 涨幅
  const change5d = (closes[closes.length - 1] - closes[closes.length - 5]) / closes[closes.length - 5] * 100;
  const change10d = (closes[closes.length - 1] - closes[closes.length - 10]) / closes[closes.length - 10] * 100;
  
  if (change10d > 15) {
    score += 15;
    signals.push(`10日涨${change10d.toFixed(1)}%`);
  } else if (change10d > 10) {
    score += 10;
    signals.push(`10日涨${change10d.toFixed(1)}%`);
  } else if (change5d > 5) {
    score += 5;
    signals.push(`5日涨${change5d.toFixed(1)}%`);
  }
  
  // 突破
  const recentHigh = Math.max(...klines.slice(-20, -1).map(k => k.high));
  if (lastClose > recentHigh) {
    score += 15;
    signals.push('突破20日高点');
  }
  
  // RSI
  const changes = [];
  for (let i = 1; i < Math.min(15, closes.length); i++) {
    changes.push(closes[i] - closes[i - 1]);
  }
  const up = changes.filter(c => c > 0).reduce((a, b) => a + b, 0);
  const down = -changes.filter(c => c < 0).reduce((a, b) => a + b, 0);
  const rsi = 100 - 100 / (1 + up / (down + 0.001));
  
  if (rsi < 40) {
    score += 10;
    signals.push(`RSI超卖${rsi.toFixed(0)}`);
  }
  
  return {
    score,
    signals,
    indicators: {
      ma5: ma5.toFixed(2),
      ma10: ma10.toFixed(2),
      ma20: ma20.toFixed(2),
      volRatio: volRatio.toFixed(2),
      rsi: rsi.toFixed(1),
      change5d: change5d.toFixed(2),
      change10d: change10d.toFixed(2)
    }
  };
}

// LLM分析 (可选)
async function llmAnalyze(stock, analysis) {
  const apiKey = process.env.SILICONFLOW_API_KEY;
  if (!apiKey) return null;
  
  const prompt = `Analyze A-share stock:
Code: ${stock.code} Name: ${stock.name}
Price: ${stock.price} CNY, Market Cap: ${stock.mv}B CNY
Score: ${analysis.score}, Signals: ${analysis.signals.join(', ')}
Indicators: MA5=${analysis.indicators.ma5}, MA10=${analysis.indicators.ma10}, RSI=${analysis.indicators.rsi}

Give: 1)Trend 2)Support/Resistance 3)1-week prediction 4)Risk level. Be concise.`;

  try {
    const body = JSON.stringify({
      model: 'Qwen/Qwen2.5-72B-Instruct',
      messages: [{ role: 'user', content: prompt }],
      max_tokens: 200
    });
    
    const result = await new Promise((resolve, reject) => {
      const req = https.request({
        hostname: 'api.siliconflow.cn',
        path: '/v1/chat/completions',
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${apiKey}`,
          'Content-Type': 'application/json'
        }
      }, (res) => {
        let data = '';
        res.on('data', (chunk) => data += chunk);
        res.on('end', () => resolve(JSON.parse(data)));
      });
      req.on('error', reject);
      req.write(body);
      req.end();
    });
    
    return result.choices?.[0]?.message?.content || null;
  } catch (e) {
    return null;
  }
}

// 主函数
async function main() {
  console.log('='.repeat(60));
  console.log('A股每周选股系统');
  console.log(`执行时间: ${new Date().toISOString()}`);
  console.log('='.repeat(60));
  
  // 1. 获取股票列表
  console.log('\n[1/3] 获取股票列表...');
  const stocks = await getStockList();
  
  if (stocks.length === 0) {
    console.log('无符合条件的股票');
    return;
  }
  
  // 2. 技术分析
  console.log('\n[2/3] 技术分析...');
  const results = [];
  
  for (let i = 0; i < stocks.length; i++) {
    const stock = stocks[i];
    
    if ((i + 1) % 20 === 0) {
      console.log(`  进度: ${i + 1}/${stocks.length}`);
    }
    
    const klines = await getKLine(stock.code, 60);
    if (klines.length < 20) continue;
    
    const analysis = analyzeStock(klines);
    if (analysis.score >= CONFIG.minScore) {
      results.push({
        ...stock,
        score: analysis.score,
        signals: analysis.signals,
        indicators: analysis.indicators
      });
    }
  }
  
  results.sort((a, b) => b.score - a.score);
  console.log(`  筛选出: ${results.length} 只潜力股`);
  
  // 3. LLM分析 (Top 5)
  console.log('\n[3/3] LLM深度分析 (Top 5)...');
  for (const stock of results.slice(0, 5)) {
    const llmResult = await llmAnalyze(stock, stock);
    if (llmResult) {
      stock.llmAnalysis = llmResult;
      console.log(`  ${stock.name}: ${llmResult.substring(0, 50)}...`);
    }
  }
  
  // 输出结果
  const topStocks = results.slice(0, CONFIG.topN);
  
  console.log('\n' + '='.repeat(60));
  console.log(`本周精选股票 (Top ${CONFIG.topN})`);
  console.log('='.repeat(60));
  
  for (let i = 0; i < topStocks.length; i++) {
    const s = topStocks[i];
    console.log(`\n${i + 1}. ${s.code} ${s.name}`);
    console.log(`   现价: ${s.price}元 | 市值: ${s.mv}亿`);
    console.log(`   评分: ${s.score}分 | 信号: ${s.signals.join(', ')}`);
    if (s.llmAnalysis) {
      console.log(`   AI分析: ${s.llmAnalysis.substring(0, 80)}...`);
    }
  }
  
  // 保存结果
  const output = {
    timestamp: new Date().toISOString(),
    top_stocks: topStocks.map(s => ({
      code: s.code,
      name: s.name,
      price: s.price,
      market_cap: s.mv,
      score: s.score,
      signals: s.signals,
      llm_analysis: s.llmAnalysis
    }))
  };
  
  // 保存到文件
  const date = new Date().toISOString().slice(0, 10).replace(/-/g, '');
  fs.writeFileSync(`weekly_pick_${date}.json`, JSON.stringify(output, null, 2));
  console.log(`\n结果已保存: weekly_pick_${date}.json`);
  
  // GitHub Actions输出
  if (process.env.GITHUB_OUTPUT) {
    const summary = topStocks.map((s, i) => `${i + 1}. ${s.code} ${s.name} - 现价${s.price}元, 评分${s.score}分`).join('\\n');
    fs.appendFileSync(process.env.GITHUB_OUTPUT, `result<<EOF\n${summary}\nEOF\n`);
  }
  
  console.log('\n' + '='.repeat(60));
  console.log('✅ 选股完成');
  console.log('='.repeat(60));
  
  return output;
}

main().catch(e => {
  console.error('错误:', e);
  process.exit(1);
});
