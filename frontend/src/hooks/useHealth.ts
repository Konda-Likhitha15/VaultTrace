import { useEffect, useState } from 'react';

export function useHealth() {
  const [available, setAvailable] = useState<boolean | null>(null);
  useEffect(() => { setAvailable(null); }, []);
  return available;
}
