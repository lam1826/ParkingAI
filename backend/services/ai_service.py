import json
from datetime import date
from typing import Optional, Dict, Any, List
from fastapi import HTTPException, status
from google import genai
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from core.config import settings

# Import trực tiếp Model AiReport của bạn
from models.ai_report import AiReport

# IMPORT THÊM ParkingService ĐỂ LẤY DỮ LIỆU DASHBOARD TỰ ĐỘNG
from services.parking_service import ParkingService

class AIService:
    """
    AIService chịu trách nhiệm giao tiếp với mô hình AI (Google Gemini)
    thông qua SDK mới (google.genai) để phân tích dữ liệu bãi đỗ xe,
    tạo báo cáo tự động và hỗ trợ truy vấn ngôn ngữ tự nhiên.
    """

    def __init__(self, db: Session, api_key: str):
        """
        Khởi tạo AI Service theo chuẩn SDK mới của Google.
        """
        self.db = db
        # Khởi tạo Client thay vì dùng genai.configure() cũ
        self.client = genai.Client(api_key=api_key)
        # Sử dụng model chuẩn khuyến nghị hiện tại
        self.model_name = 'gemini-3.6-flash'

    def generate_daily_report(self, target_date: date, parking_stats: Dict[str, Any], user_id: int) -> str:
        """
        Tạo báo cáo tổng kết hoạt động bãi đỗ xe trong ngày bằng AI.
        """
        try:
            stats_json = json.dumps(parking_stats, ensure_ascii=False, indent=2)

            system_prompt = (
                "Bạn là một AI phân tích dữ liệu chuyên nghiệp cho hệ thống quản lý bãi đỗ xe thông minh. "
                "NGUYÊN TẮC TỐI THƯỢNG: "
                "- KHÔNG ĐƯỢC tự bịa đặt, tự tạo thêm dữ liệu hoặc đưa ra các con số không có trong phần dữ liệu. "
                "- Chỉ phân tích và đưa ra nhận định dựa trên chính xác các số liệu đã cung cấp. "
                "- Format kết quả đầu ra thành văn bản rõ ràng, bắt buộc chia thành 4 phần với đúng các tiêu đề sau: "
                "  1. Tóm tắt\n"
                "  2. Đánh giá lưu lượng\n"
                "  3. Khung giờ cao điểm\n"
                "  4. Khuyến nghị"
            )

            user_prompt = f"""
DỮ LIỆU ĐẦU VÀO CHO NGÀY {target_date.strftime('%Y-%m-%d')}:
{stats_json}
"""

            final_prompt = f"{system_prompt}\n\n{user_prompt}"

            # Cú pháp gọi API mới qua client.models.generate_content
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=final_prompt,
                config={
                    "temperature": 0.2,
                }
            )

            report_text = response.text.strip()

            # Tự động lưu lịch sử vào database
            self.save_ai_report(
                report_type="DAILY_REPORT",
                prompt_used=final_prompt,
                content=report_text,
                generated_by_id=user_id
            )

            return report_text

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Lỗi khi tạo báo cáo ngày bằng AI: {str(e)}"
            )

    def generate_weekly_report(self, start_date: date, end_date: date, weekly_data: List[Dict[str, Any]], user_id: int) -> str:
        """
        Phân tích xu hướng và tạo báo cáo tổng kết tuần.
        """
        try:
            data_json = json.dumps(weekly_data, ensure_ascii=False, indent=2)

            system_prompt = (
                "Bạn là chuyên gia phân tích vận hành bãi đỗ xe. "
                "NGUYÊN TẮC TỐI THƯỢNG: "
                "- KHÔNG ĐƯỢC tự bịa đặt dữ liệu ngoài dữ liệu tuần được cung cấp. "
                "- So sánh sự biến động giữa các ngày, xác định xu hướng lưu lượng và doanh thu."
            )

            user_prompt = f"""
DỮ LIỆU TUẦN TỪ {start_date.strftime('%Y-%m-%d')} ĐẾN {end_date.strftime('%Y-%m-%d')}:
{data_json}
"""

            final_prompt = f"{system_prompt}\n\n{user_prompt}"

            response = self.client.models.generate_content(
                model=self.model_name,
                contents=final_prompt,
                config={
                    "temperature": 0.2,
                }
            )

            report_text = response.text.strip()

            self.save_ai_report(
                report_type="WEEKLY_REPORT",
                prompt_used=final_prompt,
                content=report_text,
                generated_by_id=user_id
            )

            return report_text

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Lỗi khi tạo báo cáo tuần bằng AI: {str(e)}"
            )

    def answer_question(self, question: str, parking_stats: Dict[str, Any], user_id: int) -> str:
        """
        Xử lý truy vấn ngôn ngữ tự nhiên của người dùng về dữ liệu bãi đỗ xe.
        """
        try:
            stats_json = json.dumps(parking_stats, ensure_ascii=False, indent=2)

            system_prompt = (
                "Bạn là trợ lý AI chuyên trích xuất thông tin cho hệ thống bãi đỗ xe. "
                "NGUYÊN TẮC TỐI THƯỢNG: "
                "- TUYỆT ĐỐI KHÔNG tự suy diễn, ước lượng, bịa đặt dữ liệu hay sử dụng kiến thức bên ngoài. "
                "- CHỈ sử dụng thông tin nằm trong phần 'DỮ LIỆU ĐƯỢC CUNG CẤP'. "
                "- Câu trả lời phải ngắn gọn, trực diện, đúng trọng tâm câu hỏi. "
                "- Nếu câu hỏi hỏi về thông tin không có trong 'DỮ LIỆU ĐƯỢC CUNG CẤP', bạn BẮT BUỘC phải trả lời: "
                "'Tôi không có đủ dữ liệu để trả lời câu hỏi này.'"
            )

            user_prompt = f"""
DỮ LIỆU ĐƯỢC CUNG CẤP:
{stats_json}

CÂU HỎI:
"{question}"
"""
            final_prompt = f"{system_prompt}\n\n{user_prompt}"

            response = self.client.models.generate_content(
                model=self.model_name,
                contents=final_prompt,
                config={
                    "temperature": 0.0,
                }
            )

            answer = response.text.strip()

            self.save_ai_report(
                report_type="Q_A",
                prompt_used=final_prompt,
                content=answer,
                generated_by_id=user_id
            )

            return answer

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Lỗi khi AI xử lý câu hỏi: {str(e)}"
            )

    def ask_dashboard_question(self, question: str, user_id: int) -> str:
        """
        Hỏi đáp tự động với dữ liệu từ Dashboard.
        """
        try:
            parking_service = ParkingService(self.db)
            dashboard_data = parking_service.get_dashboard_data()
            
            data_json = json.dumps(dashboard_data, ensure_ascii=False, indent=2)

            system_prompt = (
                "Bạn là trợ lý AI chuyên trích xuất thông tin cho hệ thống quản lý bãi đỗ xe. "
                "CÁC NGUYÊN TẮC BẮT BUỘC BẠN PHẢI TUÂN THỦ TUYỆT ĐỐI: "
                "1. KHÔNG ĐƯỢC tự suy diễn, phỏng đoán, tính toán thêm hay sử dụng kiến thức bên ngoài. "
                "2. CHỈ ĐƯỢC PHÉP trả lời dựa trên thông tin nằm trong phần 'DỮ LIỆU HỆ THỐNG HÔM NAY'. "
                "3. Trả lời ngắn gọn, trực diện đúng vào câu hỏi. "
                "4. Nếu câu hỏi hỏi về thông tin KHÔNG CÓ trong dữ liệu được cung cấp, BẮT BUỘC bạn phải trả lời chính xác câu sau: "
                "'Tôi không có đủ dữ liệu để trả lời câu hỏi này.'"
            )

            user_prompt = f"""
DỮ LIỆU HỆ THỐNG HÔM NAY:
{data_json}

CÂU HỎI:
"{question}"
"""
            final_prompt = f"{system_prompt}\n\n{user_prompt}"

            response = self.client.models.generate_content(
                model=self.model_name,
                contents=final_prompt,
                config={
                    "temperature": 0.0,
                }
            )

            answer = response.text.strip()

            self.save_ai_report(
                report_type="DASHBOARD_QA",
                prompt_used=final_prompt,
                content=answer,
                generated_by_id=user_id
            )

            return answer

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Lỗi khi AI xử lý câu hỏi Dashboard: {str(e)}"
            )

    def suggest_staff_schedule(
        self, 
        hourly_traffic: List[Dict[str, Any]], 
        occupancy_rate: float, 
        revenue: float,
        user_id: int
    ) -> str:
        """
        AI phân tích lưu lượng, tỷ lệ lấp đầy và doanh thu để gợi ý nhân sự.
        """
        try:
            input_data = {
                "hourly_traffic": hourly_traffic,
                "revenue": revenue,
                "occupancy_rate": occupancy_rate
            }
            data_json = json.dumps(input_data, ensure_ascii=False, indent=2)

            system_prompt = (
                "Bạn là chuyên gia điều phối nhân sự cho bãi đỗ xe. Dựa vào dữ liệu được cung cấp, "
                "hãy lập báo cáo phân tích với cấu trúc 3 phần rõ ràng:\n"
                "1. Xác định giờ cao điểm (Peak hours).\n"
                "2. Gợi ý số lượng nhân viên cần thiết.\n"
                "3. Gợi ý chia ca trực cụ thể (Shifts).\n\n"
                "NGUYÊN TẮC TỐI THƯỢNG:\n"
                "- TUYỆT ĐỐI KHÔNG tạo, bịa đặt hay ước lượng các số liệu lưu lượng hoặc doanh thu mới. "
                "- Chỉ đưa ra quyết định dựa trên chính xác số liệu đầu vào được cung cấp."
            )

            user_prompt = f"""
DỮ LIỆU ĐẦU VÀO ĐỂ PHÂN TÍCH:
{data_json}
"""

            final_prompt = f"{system_prompt}\n\n{user_prompt}"

            response = self.client.models.generate_content(
                model=self.model_name,
                contents=final_prompt,
                config={
                    "temperature": 0.0,
                }
            )

            schedule_result = response.text.strip()

            self.save_ai_report(
                report_type="STAFF_SCHEDULE",
                prompt_used=final_prompt,
                content=schedule_result,
                generated_by_id=user_id
            )

            return schedule_result

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Lỗi khi AI tạo đề xuất lịch trực: {str(e)}"
            )

    def save_ai_report(
        self, 
        report_type: str, 
        prompt_used: str, 
        content: str, 
        generated_by_id: int
    ) -> AiReport:
        """
        Lưu lại lịch sử tương tác hoặc báo cáo của AI vào cơ sở dữ liệu.
        """
        try:
            db_report = AiReport(
                report_type=report_type,
                prompt_used=prompt_used,
                content=content,
                generated_by_id=generated_by_id
            )
            
            self.db.add(db_report)
            self.db.commit()
            self.db.refresh(db_report)
            
            return db_report

        except SQLAlchemyError as db_err:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Lỗi cơ sở dữ liệu khi lưu lịch sử AI: {str(db_err)}"
            )
        except Exception as e:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Lỗi hệ thống khi lưu lịch sử AI: {str(e)}"
            )