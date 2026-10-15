"""Quy tắc eGFR -> giai đoạn CKD và nội dung hướng dẫn, dịch từ hệ thống CKD-Stage-Prediction gốc (webapp.py).

Giai đoạn được suy bằng quy tắc theo ngưỡng eGFR (không phải đầu ra của mô hình học máy) và áp dụng cho
eGFR do GRU dự đoán. Nội dung chỉ mang tính tham khảo, không thay thế tư vấn của bác sĩ.
"""

STAGE_RULES = [  # (ngưỡng dưới, tên giai đoạn)
    (90, "Giai đoạn 1"), (60, "Giai đoạn 2"), (45, "Giai đoạn 3a"),
    (30, "Giai đoạn 3b"), (15, "Giai đoạn 4"), (float("-inf"), "Giai đoạn 5"),
]


def stage_from_egfr(egfr: float) -> str:
    for lo, name in STAGE_RULES:
        if egfr >= lo:
            return name
    return STAGE_RULES[-1][1]


GUIDANCE = {
    "Giai đoạn 1": {
        "description": "Tổn thương thận nhưng chức năng bình thường hoặc cao (eGFR ≥ 90).",
        "goals": ["Làm chậm tiến triển bệnh", "Giảm nguy cơ tim mạch"],
        "dietary_focus": ["Duy trì chế độ ăn cân bằng, tốt cho tim", "Tránh thực phẩm chế biến sẵn nhiều natri", "Uống đủ nước"],
        "lifestyle": ["Tập thể dục đều đặn (ít nhất 150 phút/tuần)", "Bỏ hoàn toàn thuốc lá",
                      "Tránh thuốc giảm đau NSAID (ibuprofen, naproxen…) trừ khi bác sĩ cho phép"],
        "monitoring": ["Khám hằng năm kèm theo dõi huyết áp", "Xét nghiệm albumin niệu", "Xét nghiệm creatinine máu để tính eGFR"],
        "complications": ["Thường không có, nhưng nguyên nhân nền (đái tháo đường, tăng huyết áp) cần kiểm soát tích cực."],
    },
    "Giai đoạn 2": {
        "description": "Giảm nhẹ chức năng thận (eGFR 60–89).",
        "goals": ["Tiếp tục làm chậm tiến triển", "Kiểm soát chặt huyết áp và đường huyết"],
        "dietary_focus": ["Ăn nhạt (natri < 2.300 mg/ngày)", "Tiếp tục chế độ ăn tốt cho tim"],
        "lifestyle": ["Áp dụng tất cả khuyến nghị của Giai đoạn 1 và coi đó là then chốt."],
        "monitoring": ["Tái khám mỗi 6–12 tháng", "Theo dõi đều huyết áp, eGFR và albumin niệu"],
        "complications": ["Tăng nguy cơ tăng huyết áp. Có thể xuất hiện dấu hiệu sớm của rối loạn chuyển hóa xương."],
    },
    "Giai đoạn 3a": {
        "description": "Giảm nhẹ đến trung bình chức năng thận (eGFR 45–59).",
        "goals": ["Phòng ngừa và điều trị biến chứng", "Chuẩn bị cho quản lý tích cực hơn"],
        "dietary_focus": ["Tham khảo chuyên gia dinh dưỡng thận", "Hạn chế natri (< 2.000 mg/ngày)",
                          "Có thể cần hạn chế phospho và đạm tùy kết quả xét nghiệm"],
        "lifestyle": ["Vận động vừa phải, đều đặn", "Tự theo dõi sát huyết áp và đường huyết (nếu có đái tháo đường)"],
        "monitoring": ["Thường được chuyển khám bác sĩ chuyên khoa thận", "Tái khám mỗi 3–6 tháng",
                       "Xét nghiệm phospho, canxi, PTH và hemoglobin"],
        "complications": ["Thiếu máu", "Bệnh xương giai đoạn sớm", "Tăng huyết áp phổ biến và khó kiểm soát hơn"],
    },
    "Giai đoạn 3b": {
        "description": "Giảm trung bình đến nặng chức năng thận (eGFR 30–44).",
        "goals": ["Kiểm soát tích cực các biến chứng", "Tìm hiểu các phương pháp điều trị thay thế thận"],
        "dietary_focus": ["Tuân thủ chặt chế độ ăn cho bệnh thận (đạm, natri, kali, phospho)", "Có thể cần theo dõi lượng dịch nạp vào"],
        "lifestyle": ["Tuân thủ tất cả khuyến nghị trước đó", "Tránh kiệt sức; cân bằng vận động và nghỉ ngơi"],
        "monitoring": ["Tái khám chuyên khoa thận mỗi 3 tháng", "Xét nghiệm thường xuyên để kiểm soát biến chứng"],
        "complications": ["Thiếu máu và bệnh xương rõ rệt hơn", "Tăng nguy cơ nhiễm toan chuyển hóa"],
    },
    "Giai đoạn 4": {
        "description": "Giảm nặng chức năng thận (eGFR 15–29).",
        "goals": ["Chuẩn bị cho điều trị suy thận (lọc máu hoặc ghép thận)"],
        "dietary_focus": ["Cần chế độ ăn rất nghiêm ngặt", "Phối hợp chặt với chuyên gia dinh dưỡng thận"],
        "lifestyle": ["Thường phải hạn chế dịch", "Bảo tồn chức năng thận còn lại bằng cách tuân thủ đúng chỉ dẫn y tế"],
        "monitoring": ["Khám chuyên khoa thận mỗi 1–2 tháng", "Đánh giá tạo đường vào mạch máu để lọc máu (cầu nối động–tĩnh mạch) hoặc đăng ký ghép thận"],
        "complications": ["Nguy cơ cao của mọi biến chứng CKD", "Mệt mỏi, phù và buồn nôn trở nên phổ biến"],
    },
    "Giai đoạn 5": {
        "description": "Suy thận / bệnh thận giai đoạn cuối (eGFR < 15).",
        "goals": ["Duy trì sự sống bằng điều trị thay thế thận"],
        "dietary_focus": ["Theo chế độ ăn phù hợp với lọc máu (tùy loại lọc)", "Giới hạn chặt dịch, natri, kali và phospho"],
        "lifestyle": ["Tuân thủ lịch lọc máu là yếu tố sống còn", "Kiểm soát triệu chứng và duy trì chất lượng sống"],
        "monitoring": ["Cần giám sát y tế liên tục trong lọc máu hoặc sau ghép thận"],
        "complications": ["Tình trạng đe dọa tính mạng, cần chăm sóc y tế liên tục để kiểm soát quá tải dịch, rối loạn điện giải và ứ đọng chất thải"],
    },
}

CLUSTER_NOTES = {
    "Chuyển biến xấu": "Nhóm có độ dốc eGFR thấp nhất trong mẫu (giảm nhanh nhất).",
    "Ổn định": "Nhóm có độ dốc eGFR ở mức giữa trong mẫu. Xem độ dốc thực tế bên dưới: thường vẫn âm, nghĩa là vẫn đang giảm chậm.",
    "Cải thiện": "Nhóm có độ dốc eGFR cao nhất trong mẫu (gần ngang hoặc nhích lên). Đây là nhãn tương đối so với các nhóm còn lại, không nhất thiết eGFR tăng thật.",
}
