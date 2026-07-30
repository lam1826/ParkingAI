import React, { useState } from 'react';
import api from '../services/api';

export default function AIAssistantPage() {
  const [messages, setMessages] = useState([
    { role: 'ai', content: 'Xin chào! Tôi là trợ lý AI của ParkingAI. Tôi có thể giúp gì cho bạn hôm nay?' }
  ]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const handleSendMessage = async (e) => {
    e.preventDefault();
    if (!input.trim()) return;

    const userMessage = { role: 'user', content: input };
    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);

    try {
      const res = await api.post('/ai/ask', { 
        question: userMessage.content,
        parking_stats: {} // Giữ nguyên trường này để khớp schema
      });
      
      // Đã xóa dòng console.error sai vị trí ở đây
      // Gán dữ liệu thành công vào UI
      setMessages((prev) => [...prev, { role: 'ai', content: res.data.content }]);
      
    } catch (error) {
      // Đưa console.error xuống đúng vị trí của nó để bắt lỗi thực sự
      console.error("Lỗi từ Backend:", error.response?.data || error.message); 
      setMessages((prev) => [...prev, { role: 'ai', content: 'Xin lỗi, đã xảy ra lỗi kết nối với máy chủ AI.' }]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="p-6 h-[calc(100vh-80px)] flex flex-col">
      <h1 className="text-2xl font-bold text-gray-800 mb-4">Trợ lý AI (AI Assistant)</h1>
      
      <div className="flex-1 bg-white rounded-xl shadow-sm border p-4 flex flex-col overflow-hidden">
        <div className="flex-1 overflow-y-auto space-y-4 p-2">
          {messages.map((msg, idx) => (
            <div key={idx} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div className={`max-w-[70%] p-3 rounded-lg ${
                msg.role === 'user' 
                  ? 'bg-blue-600 text-white rounded-br-none' 
                  : 'bg-gray-100 text-gray-800 rounded-bl-none'
              }`}>
                {msg.content}
              </div>
            </div>
          ))}
          {isLoading && (
            <div className="flex justify-start">
              <div className="bg-gray-100 text-gray-500 p-3 rounded-lg rounded-bl-none italic">
                AI đang suy nghĩ...
              </div>
            </div>
          )}
        </div>

        <form onSubmit={handleSendMessage} className="mt-4 flex gap-2 border-t pt-4">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Hỏi AI về doanh thu, số lượng xe đỗ..."
            className="flex-1 px-4 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            disabled={isLoading}
          />
          <button 
            type="submit" 
            disabled={isLoading}
            className="bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700 disabled:bg-blue-300"
          >
            Gửi
          </button>
        </form>
      </div>
    </div>
  );
}