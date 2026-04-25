import React from 'react';

interface PageHeaderProps {
  title: string;
  description: string;
  icon: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
}

const PageHeader: React.FC<PageHeaderProps> = ({
  title,
  description,
  icon,
  actions,
  className = '',
}) => {
  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: '1.5rem'
      }}
      className={className}
    >
      <div>
        <h1
          style={{
            fontSize: '2rem',
            fontWeight: 700,
            marginBottom: '0.5rem',
            display: 'flex',
            alignItems: 'center',
            gap: '0.75rem'
          }}
        >
          {icon}
          {title}
        </h1>
        <p
          style={{
            fontSize: '1rem',
            color: 'var(--pf-v6-global--Color--200)'
          }}
        >
          {description}
        </p>
      </div>
      {actions && (
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          {actions}
        </div>
      )}
    </div>
  );
};

export default PageHeader;