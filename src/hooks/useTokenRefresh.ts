import { useEffect, useState, useCallback, useRef } from 'react';
import { refreshToken as refreshTokenApi } from '@/lib/api';

/**
 * Parse a JWT token and extract the payload.
 * Returns null if token is invalid.
 */
function parseJwt(token: string): { exp?: number; iat?: number } | null {
  try {
    const parts = token.split('.');
    if (parts.length !== 3) return null;
    const payload = JSON.parse(atob(parts[1]));
    return payload;
  } catch {
    return null;
  }
}

/**
 * Get the expiration time of a JWT token in milliseconds since epoch.
 * Returns null if token is invalid or has no expiration.
 */
function getTokenExpiration(token: string): number | null {
  const payload = parseJwt(token);
  if (!payload?.exp) return null;
  return payload.exp * 1000; // Convert to milliseconds
}

/**
 * Calculate time until token expires in milliseconds.
 * Returns null if token is invalid.
 */
function getTimeUntilExpiry(token: string): number | null {
  const expiration = getTokenExpiration(token);
  if (!expiration) return null;
  return expiration - Date.now();
}

export interface UseTokenRefreshOptions {
  /** How many milliseconds before expiry to trigger refresh (default: 2 minutes) */
  refreshBuffer?: number;
  /** How often to check token expiry in milliseconds (default: 30 seconds) */
  checkInterval?: number;
  /** Whether the hook is enabled (default: true) */
  enabled?: boolean;
}

export interface UseTokenRefreshResult {
  /** Increments each time token is refreshed - use as key for iframe reload */
  refreshKey: number;
  /** Whether a refresh is currently in progress */
  isRefreshing: boolean;
  /** Time until token expires in milliseconds, or null */
  timeUntilExpiry: number | null;
  /** Manually trigger a token refresh */
  forceRefresh: () => Promise<boolean>;
  /** Last error if refresh failed */
  lastError: string | null;
}

/**
 * Hook that monitors JWT token expiration and proactively refreshes before expiry.
 * 
 * Use the `refreshKey` as a `key` prop on iframes to force reload when token refreshes.
 * 
 * @example
 * ```tsx
 * const { refreshKey, isRefreshing, timeUntilExpiry } = useTokenRefresh();
 * 
 * return (
 *   <iframe
 *     key={`preview-${refreshKey}`}
 *     src={getServiceProxyAuthUrl(projectId, serviceId, port)}
 *   />
 * );
 * ```
 */
export function useTokenRefresh(options: UseTokenRefreshOptions = {}): UseTokenRefreshResult {
  const {
    refreshBuffer = 2 * 60 * 1000, // 2 minutes before expiry
    checkInterval = 30 * 1000,     // Check every 30 seconds
    enabled = true,
  } = options;

  const [refreshKey, setRefreshKey] = useState(0);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [timeUntilExpiry, setTimeUntilExpiry] = useState<number | null>(null);
  const [lastError, setLastError] = useState<string | null>(null);
  
  // Track if a refresh is already in progress to avoid duplicates
  const refreshingRef = useRef(false);

  const doRefresh = useCallback(async (): Promise<boolean> => {
    if (refreshingRef.current) {
      return false;
    }
    
    refreshingRef.current = true;
    setIsRefreshing(true);
    setLastError(null);
    
    try {
      const result = await refreshTokenApi();
      
      if (result.data?.access) {
        // Token refreshed successfully
        localStorage.setItem('accessToken', result.data.access);
        
        // Increment refresh key to trigger iframe reloads
        setRefreshKey(prev => prev + 1);
        
        // Dispatch custom event for other components to react
        window.dispatchEvent(new CustomEvent('token:refreshed', {
          detail: { timestamp: Date.now() }
        }));
        
        console.debug('[useTokenRefresh] Token refreshed successfully');
        return true;
      } else {
        const errorMsg = result.error || 'Token refresh failed';
        setLastError(errorMsg);
        console.warn('[useTokenRefresh] Token refresh failed:', errorMsg);
        return false;
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : 'Unknown error';
      setLastError(errorMsg);
      console.error('[useTokenRefresh] Token refresh error:', error);
      return false;
    } finally {
      refreshingRef.current = false;
      setIsRefreshing(false);
    }
  }, []);

  // Check token expiration periodically
  useEffect(() => {
    if (!enabled) return;

    const checkExpiration = () => {
      const token = localStorage.getItem('accessToken');
      if (!token) {
        setTimeUntilExpiry(null);
        return;
      }

      const timeLeft = getTimeUntilExpiry(token);
      setTimeUntilExpiry(timeLeft);

      // If token is about to expire (within buffer), refresh it
      if (timeLeft !== null && timeLeft > 0 && timeLeft < refreshBuffer) {
        console.debug(`[useTokenRefresh] Token expiring in ${Math.round(timeLeft / 1000)}s, refreshing...`);
        doRefresh();
      }
    };

    // Check immediately on mount
    checkExpiration();

    // Set up interval to check periodically
    const intervalId = setInterval(checkExpiration, checkInterval);

    return () => clearInterval(intervalId);
  }, [enabled, refreshBuffer, checkInterval, doRefresh]);

  // Listen for storage events (token changed in another tab)
  useEffect(() => {
    if (!enabled) return;

    const handleStorage = (event: StorageEvent) => {
      if (event.key === 'accessToken' && event.newValue) {
        // Token was updated externally, update our state
        const timeLeft = getTimeUntilExpiry(event.newValue);
        setTimeUntilExpiry(timeLeft);
        setRefreshKey(prev => prev + 1);
      }
    };

    window.addEventListener('storage', handleStorage);
    return () => window.removeEventListener('storage', handleStorage);
  }, [enabled]);

  return {
    refreshKey,
    isRefreshing,
    timeUntilExpiry,
    forceRefresh: doRefresh,
    lastError,
  };
}

export default useTokenRefresh;
