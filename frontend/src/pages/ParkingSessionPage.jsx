import React, { useState, useEffect } from 'react';
import api from '../services/api';

export default function ParkingSessionPage() {
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [licensePlate, setLicensePlate] = useState('');

  const fetchSessions = async () => {
    setLoading(true);
    try {
      const res = await api.get('/api/v1/parking-sessions?status=active');
      setSessions(res.data);
    } catch (err) {
      console.error('Lỗi lấy dữ liệu phiên đỗ:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSessions();
  }, []);

  const handleCheckIn = async (e) => {
    e.preventDefault();
    if (!licensePlate) return;
    try {
      await api.post('/api/v1/parking-sessions/check-in', { license_plate: licensePlate });
      alert('Xe vào thành công!');
      setLicensePlate('');
      fetchSessions();
    } catch (err) {
      alert(err.response?.data?.detail || 'Lỗi khi check-in');
    }
  };

  const handleCheckOut = async (sessionId) => {
    if (!window.confirm('Xác nhận cho xe này ra?')) return;
    try {
      const res = await api.post(`/api/v1/parking-sessions/check-out/${sessionId}`);
      alert(`Xe ra thành công! Phí đỗ xe: ${res.data.fee} VNĐ`);
      fetchSessions();
    } catch (err) {
      alert('Lỗi khi check-out');
    }
  };

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold text-gray-800 mb-6">Quản lý Xe Vào / Ra</h1>
      
      <div className="bg-white p-6 rounded-xl shadow-sm mb-6">
        <h2 className="text-lg font-semibold mb-4">Ghi nhận Xe Vào</h2>
        <form onSubmit={handleCheckIn} className="flex gap-4">
          <input
            type="text"
            placeholder="Nhập biển số xe (VD: 30A-12345)"
            value={licensePlate}
            onChange={(e) => setLicensePlate(e.target.value)}
            className="flex-1 px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
            required
          />
          <button type="submit" className="bg-green-600 text-white px-6 py-2 rounded-lg hover:bg-green-700">
            Check In
          </button>
        </form>
      </div>

      <div className="bg-white rounded-xl shadow-sm overflow-hidden">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="bg-gray-50 border-b">
              <th className="p-4 font-medium text-gray-600">ID</th>
              <th className="p-4 font-medium text-gray-600">Biển số</th>
              <th className="p-4 font-medium text-gray-600">Vị trí đỗ</th>
              <th className="p-4 font-medium text-gray-600">Thời gian vào</th>
              <th className="p-4 font-medium text-gray-600">Thao tác</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan="5" className="p-4 text-center">Đang tải...</td></tr>
            ) : sessions.length === 0 ? (
              <tr><td colSpan="5" className="p-4 text-center">Không có xe nào đang đỗ</td></tr>
            ) : (
              sessions.map((session) => (
                <tr key={session.id} className="border-b hover:bg-gray-50">
                  <td className="p-4">{session.id}</td>
                  <td className="p-4 font-bold">{session.vehicle?.license_plate || 'N/A'}</td>
                  <td className="p-4">{session.parking_slot?.slot_number || 'Chưa xếp'}</td>
                  <td className="p-4">{new Date(session.check_in_time).toLocaleString('vi-VN')}</td>
                  <td className="p-4">
                    <button
                      onClick={() => handleCheckOut(session.id)}
                      className="bg-red-500 text-white px-4 py-1 rounded hover:bg-red-600"
                    >
                      Check Out
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}