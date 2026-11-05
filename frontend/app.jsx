const { useEffect, useState } = React;

const money = (value) => `R$ ${Number(value).toLocaleString("en-US", { maximumFractionDigits: 0 })}`;

function Card({ label, value, hint }) {
  return <article className="card"><span>{label}</span><strong>{value}</strong><small>{hint}</small></article>;
}

function App() {
  const [dashboard, setDashboard] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch("/api/dashboard")
      .then((response) => response.ok ? response.json() : response.text().then((text) => Promise.reject(text)))
      .then(setDashboard)
      .catch(() => setError("Could not load the dashboard. Start the API and run the cleaning step first."));
  }, []);

  if (error) return <main className="shell"><div className="error">{error}</div></main>;
  if (!dashboard) return <main className="shell"><p className="loading">Loading your business view...</p></main>;

  const maxRevenue = Math.max(...dashboard.monthly.map((item) => item.revenue), 1);
  return (
    <main className="shell">
      <header>
        <div><p className="eyebrow">OLIST / BUSINESS INTELLIGENCE</p><h1>Know what is moving your store.</h1>
          <p className="subtitle">A clear view of sales, customers, and delivery performance.</p></div>
          <div className="period">{dashboard.period.from} — {dashboard.period.to}</div>
      </header>
      <section className="cards">
        <Card label="Revenue" value={money(dashboard.kpis.revenue)} hint="item prices" />
        <Card label="Orders" value={dashboard.kpis.orders.toLocaleString()} hint={`${dashboard.kpis.items.toLocaleString()} items sold`} />
        <Card label="Average order" value={money(dashboard.kpis.average_order_value)} hint="revenue per order" />
        <Card label="Delivery rate" value={`${dashboard.kpis.delivery_rate}%`} hint={`${dashboard.kpis.average_review} / 5 average review`} />
      </section>
      <section className="grid">
        <article className="panel wide"><div className="panel-title"><h2>Revenue over time</h2><span>monthly</span></div>
          <div className="bars">{dashboard.monthly.map((item) => <div className="bar-wrap" key={item.month}><div className="bar" style={{height: `${Math.max(item.revenue / maxRevenue * 100, 2)}%`}} title={money(item.revenue)}></div><small>{item.month.slice(2)}</small></div>)}</div>
        </article>
        <article className="panel"><div className="panel-title"><h2>Top categories</h2><span>revenue</span></div>
          {dashboard.categories.map((item) => <div className="row" key={item.name}><span>{item.name.replaceAll("_", " ")}</span><strong>{money(item.revenue)}</strong></div>)}
        </article>
        <article className="panel"><div className="panel-title"><h2>Best states</h2><span>revenue</span></div>
          {dashboard.states.map((item) => <div className="row" key={item.name}><span>{item.name}</span><strong>{money(item.revenue)}</strong></div>)}
        </article>
      </section>
      <footer>{dashboard.data_note}</footer>
    </main>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
