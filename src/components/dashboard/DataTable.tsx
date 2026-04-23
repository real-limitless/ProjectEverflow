import { Table, Thead, Tr, Th, Tbody, Td } from '@patternfly/react-table';
import dashboardData from '@/data/dashboardMetrics.json';

export const DataTable = () => {
  const { recentActivity } = dashboardData;

  return (
    <Table variant="compact">
      <Thead>
        <Tr>
          <Th>Name</Th>
          <Th>Email</Th>
          <Th>Status</Th>
          <Th>Date</Th>
        </Tr>
      </Thead>
      <Tbody>
        {recentActivity.map((row, idx) => (
          <Tr key={idx}>
            <Td>{row.name}</Td>
            <Td>{row.email}</Td>
            <Td>{row.status}</Td>
            <Td>{row.date}</Td>
          </Tr>
        ))}
      </Tbody>
    </Table>
  );
};
