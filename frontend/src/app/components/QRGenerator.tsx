import { useState, useEffect, useRef, useCallback } from 'react';
import QRCode from 'qrcode';
import { Download } from 'lucide-react';

interface QRGeneratorProps {
  refId: string;
  /** Encoded into the QR image (e.g. redirect URL). Defaults to refId. */
  encodePayload?: string;
  whatsappMessage?: string;
  onGenerated?: (dataUrl: string) => void;
}

export function QRGenerator({ refId, encodePayload, whatsappMessage, onGenerated }: QRGeneratorProps) {
  const [qrDataUrl, setQrDataUrl] = useState<string>('');
  const canvasRef = useRef<HTMLCanvasElement>(null);

  const generateQR = useCallback(async () => {
    if (!canvasRef.current || !refId) return;

    const data = encodePayload?.trim() || refId;

    try {
      await QRCode.toCanvas(canvasRef.current, data, {
        width: 200,
        margin: 2,
        color: {
          dark: '#000000ff',
          // Transparent “quiet zone” / background so PNG has no solid backdrop
          light: '#00000000',
        },
      });

      const dataUrl = canvasRef.current.toDataURL('image/png');
      setQrDataUrl(dataUrl);
      onGenerated?.(dataUrl);
    } catch (err) {
      console.error('Error generating QR code:', err);
    }
  }, [refId, encodePayload, onGenerated]);

  useEffect(() => {
    if (refId) {
      void generateQR();
    }
  }, [refId, whatsappMessage, generateQR]);

  const handleDownload = () => {
    if (!qrDataUrl) return;

    const link = document.createElement('a');
    link.download = `qr-${refId}.png`;
    link.href = qrDataUrl;
    link.click();
  };

  return (
    <div className="flex flex-col items-center gap-3">
      <div
        className="rounded-lg border border-dashed border-gray-300 bg-gray-100 p-1"
        title="Gray area is only for preview; downloaded PNG uses a transparent background"
      >
        <canvas
          ref={canvasRef}
          className="block w-40 h-40 sm:w-[200px] sm:h-[200px] max-w-full rounded-md"
        />
      </div>
      {qrDataUrl && (
        <button
          onClick={handleDownload}
          className="flex w-full items-center justify-center gap-2 px-3 py-2 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors sm:w-auto"
        >
          <Download className="w-4 h-4" />
          Download QR
        </button>
      )}
    </div>
  );
}
