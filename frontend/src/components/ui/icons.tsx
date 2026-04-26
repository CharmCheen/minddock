import React from 'react';

interface IconProps {
  size?: number;
  className?: string;
  style?: React.CSSProperties;
}

const IconBase: React.FC<IconProps & { children: React.ReactNode }> = ({ size = 16, className, style, children }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={2}
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
    style={style}
  >
    {children}
  </svg>
);

export const IconBooks: React.FC<IconProps> = (props) => (
  <IconBase {...props}>
    <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
    <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
    <path d="M6.5 2H20" />
    <path d="M9 7h6" />
    <path d="M9 11h6" />
  </IconBase>
);

export const IconBookOpen: React.FC<IconProps> = (props) => (
  <IconBase {...props}>
    <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z" />
    <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z" />
  </IconBase>
);

export const IconRefresh: React.FC<IconProps> = (props) => (
  <IconBase {...props}>
    <path d="M23 4v6h-6" />
    <path d="M1 20v-6h6" />
    <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
  </IconBase>
);

export const IconPlug: React.FC<IconProps> = (props) => (
  <IconBase {...props}>
    <path d="M12 22v-5" />
    <path d="M15 8V2" />
    <path d="M9 8V2" />
    <path d="M15 8a3 3 0 0 1 3 3v4a3 3 0 0 1-3 3H9a3 3 0 0 1-3-3v-4a3 3 0 0 1 3-3h6z" />
    <path d="M6 14h12" />
  </IconBase>
);

export const IconFolderOpen: React.FC<IconProps> = (props) => (
  <IconBase {...props}>
    <path d="M5 19a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v2" />
    <path d="M13.3 17H19a2 2 0 0 0 2-2v-2a2 2 0 0 0-2-2h-5.7l-2 3.5z" />
  </IconBase>
);

export const IconLink: React.FC<IconProps> = (props) => (
  <IconBase {...props}>
    <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
    <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
  </IconBase>
);

export const IconFileText: React.FC<IconProps> = (props) => (
  <IconBase {...props}>
    <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z" />
    <polyline points="14 2 14 8 20 8" />
    <line x1="16" y1="13" x2="8" y2="13" />
    <line x1="16" y1="17" x2="8" y2="17" />
    <line x1="10" y1="9" x2="8" y2="9" />
  </IconBase>
);

export const IconSearch: React.FC<IconProps> = (props) => (
  <IconBase {...props}>
    <circle cx="11" cy="11" r="8" />
    <line x1="21" y1="21" x2="16.65" y2="16.65" />
  </IconBase>
);

export const IconX: React.FC<IconProps> = (props) => (
  <IconBase {...props}>
    <line x1="18" y1="6" x2="6" y2="18" />
    <line x1="6" y1="6" x2="18" y2="18" />
  </IconBase>
);

export const IconTrash: React.FC<IconProps> = (props) => (
  <IconBase {...props}>
    <polyline points="3 6 5 6 21 6" />
    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
    <line x1="10" y1="11" x2="10" y2="17" />
    <line x1="14" y1="11" x2="14" y2="17" />
  </IconBase>
);

export const IconSpinner: React.FC<IconProps> = (props) => (
  <IconBase {...props}>
    <path d="M12 2v4" opacity="0.3" />
    <path d="M12 18v4" opacity="0.3" />
    <path d="M4.93 4.93l2.83 2.83" opacity="0.3" />
    <path d="M16.24 16.24l2.83 2.83" opacity="0.3" />
    <path d="M2 12h4" opacity="0.3" />
    <path d="M18 12h4" opacity="0.3" />
    <path d="M4.93 19.07l2.83-2.83" opacity="0.3" />
    <path d="M16.24 7.76l2.83-2.83" opacity="0.3" />
    <path d="M12 2A10 10 0 0 1 22 12" />
  </IconBase>
);
