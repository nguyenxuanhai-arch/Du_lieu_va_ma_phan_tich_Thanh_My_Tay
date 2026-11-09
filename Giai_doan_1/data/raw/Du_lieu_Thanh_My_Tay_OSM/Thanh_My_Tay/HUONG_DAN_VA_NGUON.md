# Dữ liệu bản đồ phường Thạnh Mỹ Tây, TP.HCM

## Phạm vi và nguồn

- Dữ liệu: © OpenStreetMap contributors, trích xuất Việt Nam do Geofabrik cung cấp.
- Nguồn tải: https://download.geofabrik.de/asia/vietnam-latest.osm.pbf
- Thời điểm dữ liệu trong header bản nguồn: **2026-11-02T21:21:26Z** (UTC). Ngày tải và xử lý: 03/11/2026 UTC.
- MD5 bản nguồn đã đối chiếu với Geofabrik: `b95adf1b52c1cc55d5ef6dd1db008444`.
- Ranh giới lọc: OpenStreetMap relation **19260956**, tên **Phường Thạnh Mỹ Tây**, phiên bản 29. https://www.openstreetmap.org/relation/19260956
- Polygon được ghép từ các way có vai trò outer của relation; diện tích hình học khoảng 4,442 km², tính trên ellipsoid WGS84. Đây là giá trị tính từ OSM, không phải diện tích pháp lý.
- Tọa độ các lớp GeoJSON: WGS84, thứ tự **kinh độ, vĩ độ**.
- Khoản 45 Điều 1 Nghị quyết 1685/NQ-UBTVQH15 nêu phường được hình thành từ Phường 19, 22 và 25. Văn bản xác nhận thành phần sáp nhập, không xác nhận độ chính xác từng đỉnh polygon OSM.
- Nguồn pháp lý: https://xaydungchinhsach.chinhphu.vn/toan-van-nghi-quyet-so-1685-nq-ubtvqh15-sap-xep-cac-dvhc-cap-xa-cua-thanh-pho-ho-chi-minh-nam-2025-119250616211341304.htm
- Giấy phép dữ liệu: ODbL 1.0. https://www.openstreetmap.org/copyright và https://opendatacommons.org/licenses/odbl/1-0/

## Các tệp

| Tệp | Nội dung và cách dùng |
|---|---|
| `ranh_gioi.geojson` | Polygon OSM dùng để lọc. |
| `duong_giao_thong.geojson` | Các OSM way có thuộc tính highway, đã cắt hình học theo ranh phường. Có thể gồm đường ô tô, hẻm, đường đi bộ, bậc thang, đường nội bộ... Không được coi tất cả là đường xe máy được phép đi. |
| `dia_diem_va_nut_co_thuoc_tinh.geojson` | Các node có tag nằm trong hoặc trên ranh: địa điểm, biển báo, đèn tín hiệu, điểm dừng... tùy mức độ được cộng đồng ghi nhận. |
| `doi_tuong_khac.geojson` | Các way khác giao với phường: tòa nhà, mặt nước, sử dụng đất... Đối tượng được biểu diễn dạng đường hoặc polygon theo tag; không phải bản dựng đầy đủ mọi multipolygon relation. |
| `thanh_my_tay.osm.pbf` | Bản OSM cục bộ, giữ nguyên tag và tham chiếu để lập trình, dựng mạng đường. Xem quy tắc chọn bên dưới. |
| `ban_do_kiem_tra.png` | Hình kiểm tra trực quan mạng đường và ranh giới. |
| `thong_ke.json` | Số đối tượng được chọn; số way không đồng nghĩa số tuyến đường có tên. |
| `kiem_tra_chat_luong.json` | Kiểm tra tham chiếu OSM và tính hợp lệ/phạm vi của các lớp GeoJSON. |
| `SHA256SUMS.txt` | Mã kiểm tra các tệp trong gói. |

## Quy trình lọc và nhật ký xử lý

1. Giữ nguyên bản nguồn quốc gia trong quá trình xử lý; không đưa bản quốc gia vào gói giao.
2. Dựng polygon từ ranh OSM và kiểm tra hình học hợp lệ.
3. Chọn node được polygon bao phủ. Chọn way có hình học giao với polygon, kể cả đường đi qua ranh.
4. Xuất GeoJSON bằng phép giao hình học với polygon. Các polygon way không hợp lệ được sửa bằng buffer(0) trước khi giao; đây là cách xử lý kỹ thuật, không phải xác minh ngoài thực địa.
5. Với PBF, giữ nguyên way được chọn và bổ sung các node tham chiếu để tránh đứt hình học. Bổ sung restriction và multipolygon relation có way thành viên được chọn, cùng đối tượng tham chiếu. Không lấy toàn bộ tuyến xe buýt, ranh cấp tỉnh/quốc gia chỉ vì có thành viên giao phường.
6. Vì bảo toàn tham chiếu, **PBF có thể chứa phần kéo dài ngoài ranh của các đối tượng liên quan**. Đây không phải tệp chỉ chứa mọi tọa độ bên trong phường. Các GeoJSON mới là các lớp đã cắt theo ranh.
7. Kiểm tra không thiếu node/way/relation được tham chiếu trong PBF; kiểm tra GeoJSON hợp lệ và nằm trong polygon (sai số kiểm tra 1e-9 độ).

## Dùng cho ứng dụng tìm đường

- Mở GeoJSON trong QGIS để xem và kiểm tra. Dùng PBF với công cụ hỗ trợ OSM để dựng mạng đường.
- Dựng cạnh từ các node dùng chung; phân biệt cầu/hầm, layer, đường một chiều, loại phương tiện, access, motor_vehicle, motorcycle và restriction. Không nối mọi giao cắt hình học thành ngã giao.
- Ô/tag thiếu nghĩa là **nguồn chưa ghi nhận**, không phải 0, hai chiều hay mặc nhiên được phép đi.
- Chưa xử lý thành đồ thị định tuyến hoàn chỉnh; chưa kiểm chứng tính thông hành thực tế hay mọi hạn chế rẽ theo phương tiện.
- Tệp chỉ bao phủ dữ liệu đã có trong OSM; không bảo đảm mọi hẻm, cửa ra vào, biển báo ngoài thực địa đều đã được ghi nhận.
- Không có lưu lượng, vận tốc thực đo, lịch sử thời gian chờ, ùn tắc thời gian thực hay dữ liệu camera. Không dùng lớp bản đồ này để tự khẳng định tuyến nào ít kẹt xe nhất.
- Các hành trình cần vòng ra ngoài phường có thể không tìm đủ phương án với gói cục bộ này; phạm vi giao được giới hạn theo yêu cầu.

## Trích nguồn gợi ý

OpenStreetMap contributors. Dữ liệu OpenStreetMap khu vực phường Thạnh Mỹ Tây, trích từ Geofabrik Vietnam, mốc dữ liệu 02/11/2026 21:21:26 UTC; truy cập và xử lý 03/11/2026 UTC. Giấy phép ODbL 1.0.

Giữ dòng ghi công “© OpenStreetMap contributors” khi hiển thị bản đồ và tuân thủ điều kiện ODbL khi phân phối dữ liệu dẫn xuất.
