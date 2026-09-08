import type { Metadata } from 'next';
import { readPharmacyPublication } from '../../../lib/pharmacy-publication.mjs';
import { PharmacyPayments } from './pharmacy-payments';

export const metadata: Metadata = { title: 'Recursos da saúde' };

export default function HealthResourcesPage() {
  // No public database projection is enabled yet. Never substitute private
  // captures or demonstration records for reviewed public data.
  const publication = readPharmacyPublication(null);
  return <main><header className="site-header"><a href="/recursos">← Recursos de Barreiras</a></header>
    <PharmacyPayments publication={publication}/></main>;
}
