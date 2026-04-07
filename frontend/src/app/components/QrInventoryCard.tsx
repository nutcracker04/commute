import { QRGenerator } from './QRGenerator';
import type { QrItem } from '../lib/adminApi';

function formatTs(sec: number | null | undefined): string {
  if (sec == null) return '—';
  return new Date(sec * 1000).toLocaleString();
}

interface QrInventoryCardProps {
  item: QrItem;
}

export function QrInventoryCard({ item }: QrInventoryCardProps) {
  const scanned = item.last_scanned_at != null;

  return (
    <div className="border border-gray-200 rounded-lg p-3 sm:p-4 space-y-3 bg-white">
      <div className="space-y-1">
        <div className="text-xs font-mono font-medium text-gray-900">QR #{item.id}</div>
        <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-gray-500">
          <span>Provisioned: {formatTs(item.provisioned_at)}</span>
        </div>
        <div className="text-[11px]">
          <span
            className={
              scanned ? 'text-green-700 font-medium' : 'text-amber-700 font-medium'
            }
          >
            {scanned ? `Last scanned ${formatTs(item.last_scanned_at)}` : 'Not scanned yet'}
          </span>
          {item.expires_at != null && (
            <span className="text-gray-500 ml-2">Session expires: {formatTs(item.expires_at)}</span>
          )}
        </div>
      </div>

      <QRGenerator
        refId={String(item.id)}
        encodePayload={item.redirect_url}
        whatsappMessage={item.full_prefilled_text}
      />

      <div className="pt-2 border-t border-gray-200">
        <div className="text-xs font-medium text-gray-700 mb-1">Prefilled WhatsApp text</div>
        <div className="text-xs text-gray-600 bg-gray-50 p-2 rounded max-h-24 overflow-y-auto whitespace-pre-wrap break-words">
          {item.full_prefilled_text}
        </div>
        <div className="mt-2 text-[11px] text-gray-500 break-all">
          <span className="font-medium text-gray-700">Redirect: </span>
          {item.redirect_url}
        </div>
      </div>
    </div>
  );
}
