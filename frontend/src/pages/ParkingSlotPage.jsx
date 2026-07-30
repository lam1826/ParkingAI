import React, { useState, useEffect } from 'react';
import api from '../services/api';

export default function ParkingSlotPage() {
  const [slots, setSlots] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const fetchSlots = async () => {
      setLoading(true);
      try {
        const res = await api.get('/api/v1/parking-slots'); 
// Lưu ý: Nếu backend của bạn định nghĩa là gạch dưới, hãy đổi thành '/api/v1/parking_slots'
        setSlots(res.data);
      } catch (error) {
        console.error('Lỗi khi tải vị trí đỗ:', error);
      } finally {
        setLoading(false);
      }
    };
    fetchSlots();
  }, []);

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold text-gray-800 mb-6">Trạng thái Vị trí đỗ</h1>
      
      {loading ? (
        <p>Đang tải dữ liệu...</p>
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
          {slots.map((slot) => (
            <div 
              key={slot.id} 
              className={`p-4 rounded-xl border shadow-sm text-center flex flex-col justify-center items-center h-32 transition ${
                slot.is_occupied ? 'bg-red-50 border-red-200' : 'bg-green-50 border-green-200'
              }`}
            >
              <span className="text-xl font-bold text-gray-700">{slot.slot_number}</span>
              <span className={`mt-2 px-3 py-1 rounded-full text-xs font-semibold ${
                slot.is_occupied ? 'bg-red-100 text-red-700' : 'bg-green-100 text-green-700'
              }`}>
                {slot.is_occupied ? 'Đang đỗ' : 'Trống'}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}