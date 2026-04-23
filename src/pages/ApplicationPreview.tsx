import { useParams } from 'react-router-dom';

import { LegacyHierarchyRouteRedirect } from '../components/project/LegacyHierarchyRouteRedirect';

const ApplicationPreview = () => {
  const { appName } = useParams();

  return (
    <LegacyHierarchyRouteRedirect
      projectIdentifier={appName}
      message="Redirecting to the hierarchy route for this project..."
    />
  );
};

export default ApplicationPreview;
