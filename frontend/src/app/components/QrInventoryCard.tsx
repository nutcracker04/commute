import { useState } from 'react';
import { Trash2 } from 'lucide-react';
import { QRGenerator } from './QRGenerator';
import { deleteQr, type QrItem } from '../lib/adminApi';

function formatTs(sec: number | null | undefined): string {
  if (sec == null) return '—';
  return new Date(sec * 1000).toLocaleString();
}

interface QrInventoryCardProps {
  item: QrItem;
  /** When provided, a delete button is shown; called with the QR id after a successful delete. */
  onDeleted?: (id: number) => void;
}

export function QrInventoryCard({ item, onDeleted }: QrInventoryCardProps) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleDelete = async () => {
    if (!window.confirm(`Delete QR #${item.id}? This cannot be undone.`)) return;
    setBusy(true);
    setError(null);
    try {
      await deleteQr(item.id);
      onDeleted?.(item.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Delete failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="border border-gray-200 rounded-lg p-3 sm:p-4 space-y-3 bg-white">
      <div className="flex items-start justify-between gap-2">
        <div className="space-y-1">
          <div className="text-xs font-mono font-medium text-gray-900">QR #{item.id}</div>
          <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-gray-500">
            <span>Provisioned: {formatTs(item.provisioned_at)}</span>
          </div>
        </div>
        {onDeleted && (
          <button
            type="button"
            onClick={() => void handleDelete()}
            disabled={busy}
            title={`Delete QR #${item.id}`}
            aria-label={`Delete QR #${item.id}`}
            className="inline-flex size-8 shrink-0 items-center justify-center rounded-md text-gray-400 transition-colors hover:bg-red-50 hover:text-red-600 disabled:opacity-50"
          >
            <Trash2 className="size-4" />
          </button>
        )}
      </div>

      {error && (
        <div className="rounded-md border border-red-200 bg-red-50 px-2 py-1 text-[11px] text-red-800">
          {error}
        </div>
      )}

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
