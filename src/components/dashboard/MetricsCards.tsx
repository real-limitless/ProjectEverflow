import { Grid, GridItem, Card, CardBody, CardTitle } from '@patternfly/react-core';
import dashboardData from '@/data/dashboardMetrics.json';

export const MetricsCards = () => {
  const { metrics } = dashboardData;

  return (
    <Grid hasGutter>
      {metrics.map((metric, idx) => (
        <GridItem key={idx} span={12} sm={6} lg={3}>
          <Card>
            <CardTitle>{metric.title}</CardTitle>
            <CardBody>
              <div style={{ fontSize: '2rem', fontWeight: 700 }}>{metric.value}</div>
              <div style={{ color: 'var(--pf-v6-global--success-color--100)', fontSize: '0.875rem' }}>
                {metric.change}
              </div>
            </CardBody>
          </Card>
        </GridItem>
      ))}
    </Grid>
  );
};
