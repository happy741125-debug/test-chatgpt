const sections = [
  ["需要你決定", "0"],
  ["需要你處理", "0"],
  ["需要追蹤", "0"],
  ["風險", "0"],
  ["團隊處理中", "0"],
  ["值得知道", "0"],
] as const;

export default function Home() {
  return (
    <main>
      <p className="eyebrow">WORK INTELLIGENCE HUB</p>
      <h1>貨達營運情報中樞</h1>
      <p className="lede">第一個 Sprint 正在建立 LINE 資料入口。Dashboard 將在後續階段接上真實情報。</p>
      <section aria-label="今日情報" className="grid">
        {sections.map(([label, value]) => (
          <article key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
          </article>
        ))}
      </section>
      <aside>LINE 群組目前採 Silent Mode：收集、保存、分析，但不在群組回覆。</aside>
    </main>
  );
}
