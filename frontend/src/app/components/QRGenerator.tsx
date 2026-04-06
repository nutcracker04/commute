import { useState, useEffect, useRef } from 'react';
import QRCode from 'qrcode';
import { Download } from 'lucide-react';

interface QRGeneratorProps {
  refId: string;
  whatsappMessage: string;
  onGenerated?: (dataUrl: string) => void;
}

export function QRGenerator({ refId, whatsappMessage, onGenerated }: QRGeneratorProps) {
  const [qrDataUrl, setQrDataUrl] = useState<string>('');
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    if (refId) {
      generateQR();
    }
  }, [refId, whatsappMessage]);

  const generateQR = async () => {
    if (!canvasRef.current || !refId) return;

    try {
      // Generate QR code with the ref ID as the data
      await QRCode.toCanvas(canvasRef.current, refId, {
        width: 200,
        margin: 2,
        color: {
          dark: '#000000',
          light: '#FFFFFF',
        },
      });

      const dataUrl = canvasRef.current.toDataURL('image/png');
      setQrDataUrl(dataUrl);
      onGenerated?.(dataUrl);
    } catch (err) {
      console.error('Error generating QR code:', err);
    }
  };

  const handleDownload = () => {
    if (!qrDataUrl) return;

    const link = document.createElement('a');
    link.download = `qr-${refId}.png`;
    link.href = qrDataUrl;
    link.click();
  };

  return (
    <div className="flex flex-col items-center gap-3">
      <canvas ref={canvasRef} className="border border-gray-300 rounded-lg" />
      {qrDataUrl && (
        <button
          onClick={handleDownload}
          className="flex items-center gap-2 px-3 py-1.5 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
        >
          <Download className="w-4 h-4" />
          Download QR
        </button>
      )}
    </div>
  );
}
