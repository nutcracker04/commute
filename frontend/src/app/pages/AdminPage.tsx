import { useState } from 'react';
import { QrCode, Plus, Download } from 'lucide-react';
import { QRGenerator } from '../components/QRGenerator';

interface QRCodeData {
  id: string;
  refId: string;
  whatsappMessage: string;
  createdAt: Date;
}

// Auto-generate reference ID
const generateRefId = (index: number): string => {
  const timestamp = Date.now();
  return `QR-${timestamp}-${String(index).padStart(3, '0')}`;
};

// Auto-generate WhatsApp message
const generateWhatsAppMessage = (refId: string): string => {
  return `Thanks for scanning! Your reference ID is ${refId}. We'll be in touch soon.`;
};

export function AdminPage() {
  const [quantity, setQuantity] = useState<string>('1');
  const [generatedQRs, setGeneratedQRs] = useState<QRCodeData[]>([]);
  const [isGenerating, setIsGenerating] = useState(false);

  const handleGenerate = () => {
    const qty = parseInt(quantity);
    
    if (isNaN(qty) || qty < 1 || qty > 100) {
      alert('Please enter a valid quantity between 1 and 100');
      return;
    }

    setIsGenerating(true);

    // Generate QR codes with auto-generated ref IDs and messages
    const newQRs: QRCodeData[] = [];
    for (let i = 0; i < qty; i++) {
      const refId = generateRefId(i + 1);
      const whatsappMessage = generateWhatsAppMessage(refId);
      
      newQRs.push({
        id: `qr-${Date.now()}-${i}`,
        refId,
        whatsappMessage,
        createdAt: new Date(),
      });
    }

    setGeneratedQRs([...newQRs, ...generatedQRs]);
    setQuantity('1');
    setIsGenerating(false);
  };

  const downloadAllQRs = () => {
    // This would trigger download of all QR codes
    alert('Downloading all QR codes... (Feature to be implemented)');
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="mb-8">
          <div className="flex items-center gap-3 mb-2">
            <QrCode className="w-8 h-8 text-purple-600" />
            <h1 className="text-gray-900">QR Code Admin Panel</h1>
          </div>
          <p className="text-gray-600">
            Generate QR codes with auto-generated reference IDs and WhatsApp messages
          </p>
        </div>

        {/* Generation Form */}
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6 mb-6">
          <h2 className="font-semibold text-gray-900 mb-4">Generate QR Codes</h2>
          
          <div className="flex flex-col sm:flex-row gap-4 items-start sm:items-end">
            <div className="flex-1 max-w-xs">
              <label htmlFor="quantity" className="block text-sm font-medium text-gray-700 mb-1">
                Quantity <span className="text-red-500">*</span>
              </label>
              <input
                type="number"
                id="quantity"
                min="1"
                max="100"
                placeholder="Enter quantity"
                value={quantity}
                onChange={(e) => setQuantity(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-purple-500 focus:border-transparent"
              />
              <p className="text-xs text-gray-500 mt-1">Maximum 100 QR codes per batch</p>
            </div>

            <button
              onClick={handleGenerate}
              disabled={isGenerating}
              className="flex items-center gap-2 px-6 py-2 bg-purple-600 text-white rounded-md hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              <Plus className="w-4 h-4" />
              {isGenerating ? 'Generating...' : 'Generate QR Codes'}
            </button>
          </div>

          <div className="mt-4 p-4 bg-blue-50 border border-blue-200 rounded-md">
            <p className="text-sm text-blue-800">
              <strong>Note:</strong> Reference IDs and WhatsApp messages will be auto-generated for each QR code.
            </p>
          </div>
        </div>

        {/* Generated QR Codes */}
        {generatedQRs.length > 0 && (
          <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-semibold text-gray-900">
                Generated QR Codes ({generatedQRs.length})
              </h2>
              <button
                onClick={downloadAllQRs}
                className="flex items-center gap-2 px-4 py-2 border border-gray-300 text-gray-700 rounded-md hover:bg-gray-50 transition-colors"
              >
                <Download className="w-4 h-4" />
                Download All
              </button>
            </div>
            
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
              {generatedQRs.map((qr) => (
                <div key={qr.id} className="border border-gray-200 rounded-lg p-4 space-y-3">
                  <div>
                    <div className="text-sm font-medium text-gray-900 mb-1">{qr.refId}</div>
                    <div className="text-xs text-gray-500">
                      {qr.createdAt.toLocaleString()}
                    </div>
                  </div>
                  
                  <QRGenerator
                    refId={qr.refId}
                    whatsappMessage={qr.whatsappMessage}
                  />
                  
                  <div className="pt-2 border-t border-gray-200">
                    <div className="text-xs font-medium text-gray-700 mb-1">WhatsApp Message:</div>
                    <div className="text-xs text-gray-600 bg-gray-50 p-2 rounded">
                      {qr.whatsappMessage}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}