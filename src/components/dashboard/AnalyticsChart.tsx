import dashboardData from '@/data/dashboardMetrics.json';

export const AnalyticsChart = () => {
  const { analytics } = dashboardData;
  const { data, labels } = analytics;

  return (
    <div style={{ padding: '1rem' }}>
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: '0.5rem', height: '200px' }}>
        {data.map((value, idx) => (
          <div key={idx} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
            <div
              style={{
                width: '100%',
                backgroundColor: 'var(--pf-v6-global--primary-color--100)',
                height: `${(value / Math.max(...data)) * 100}%`,
                borderRadius: '4px 4px 0 0'
              }}
            />
            <div style={{ marginTop: '0.5rem', fontSize: '0.75rem' }}>{labels[idx]}</div>
          </div>
        ))}
      </div>
    </div>
  );
};
