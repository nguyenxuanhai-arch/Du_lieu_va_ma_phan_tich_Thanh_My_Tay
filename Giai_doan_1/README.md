# Mạng hẻm Thạnh Mỹ Tây | Phân tích dữ liệu thứ cấp

## Phạm vi và nguồn

- **Đề cương Phương pháp nghiên cứu nhóm 3**, Mục 3, 4, 6 và 7 là căn cứ về câu hỏi, phạm vi và cách đánh giá. Phần xử lý dữ liệu áp dụng nội dung Buổi 7 trên LMS về giữ dữ liệu gốc, ghi đơn vị và lưu nhật ký. Bố cục kết quả bám các mục 4.1–4.3 của sườn IMRaD.
- **Mạng đường** do OpenStreetMap contributors cung cấp, bản Việt Nam từ [Geofabrik](https://download.geofabrik.de/asia/vietnam.html). Bản nguồn có thời điểm 02/11/2026 21:21:26 UTC (04:21:26 ngày 03/11/2026 giờ Việt Nam). Theo hồ sơ trong ZIP gốc, bản Việt Nam được tải ngày 03/11/2026 UTC. Gói cục bộ được lấy lại để phân tích ngày 09/11/2026 và có 9 mã SHA-256 nội bộ đã kiểm tra. Tệp PBF cục bộ không lưu mốc replication trong header, nên thời điểm trên lấy từ hồ sơ bản nguồn trong ZIP.
- **Ranh giới** là [OSM relation 19260956](https://www.openstreetmap.org/relation/19260956), phiên bản 29. Ngày 09/11/2026, polygon ghép từ các thành phần outer trong [OSM API](https://api.openstreetmap.org/api/0.6/relation/19260956/full.json) trùng hình học với polygon lưu trong ZIP. Tệp đối chiếu chỉ giữ ID, phiên bản, tọa độ và thành phần outer. [Khoản 45 Điều 1 Nghị quyết 1685/NQ-UBTVQH15](https://xaydungchinhsach.chinhphu.vn/toan-van-nghi-quyet-so-1685-nq-ubtvqh15-sap-xep-cac-dvhc-cap-xa-cua-thanh-pho-ho-chi-minh-nam-2025-119250616211341304.htm) xác nhận phường được lập từ Phường 19, 22 và 25. Văn bản được dùng đối chiếu tên và thành phần hành chính. Hình học phục vụ phân tích lấy từ OSM.
- **Phương pháp kỹ thuật** dựa vào [OSMnx](https://osmnx.readthedocs.io/en/stable/user-reference.html), [NetworkX](https://networkx.org/documentation/stable/reference/algorithms/shortest_paths.html) và quy ước OSM về [hẻm](https://wiki.openstreetmap.org/wiki/Tag:service%3Dalley), [quyền đi xe máy](https://wiki.openstreetmap.org/wiki/Key:motorcycle), [hạn chế rẽ](https://wiki.openstreetmap.org/wiki/Relation:restriction). © OpenStreetMap contributors, [ODbL 1.0](https://www.openstreetmap.org/copyright) cho dữ liệu OSM và các lớp dẫn xuất từ OSM.

## Định nghĩa và xử lý

1. Đồ thị dùng ID nút OSM chung để nối đường. Đường cắt ranh có nút mới theo từng way. Phép cắt và đo chiều dài dùng WGS 84 / UTM 48N, EPSG:32648. GeoJSON xuất ở EPSG:4326 theo thứ tự kinh độ, vĩ độ. Một way là một đối tượng OSM có thể chỉ biểu diễn một phần của tuyến đường.
2. Nhãn hẻm dựa trên `service=alley` hoặc tên bắt đầu bằng “Hẻm”. Bốn trục nghiên cứu được chọn bằng tên trong đề cương. Đường còn lại trong mô hình được xếp nhóm khác, gồm cả đường dịch vụ chưa có dấu hiệu là hẻm. Cách nhận diện này có thể bỏ sót hẻm thiếu thẻ hoặc tên.
3. Chiều đi ưu tiên `oneway:motorcycle`, sau đó `oneway:motor_vehicle`, rồi `oneway`. Quyền đi ưu tiên motorcycle → motor_vehicle → vehicle → access. Tệp kiểm tra way giữ các tag gốc và lý do loại. Cổng chắn chưa có quyền đi rõ bị khóa chuyển tiếp. Mô hình không cho quay đầu trực tiếp. Có 7 relation áp dụng qua nút, 21 relation có ngoại lệ xe máy và 2 relation via-way chưa giải mã, dẫn đến tạm loại 3 way via. Lượt này đánh giá theo giả định lọc thận trọng nên một số tuyến thực địa có thể bị loại hoặc bản đồ còn thiếu biển cấm.
4. OSMnx giữ các đầu mút, điểm đấu nối, các nút cần áp hạn chế và nút cắt ranh. Nút bậc một trên đồ thị vô hướng toàn mạng, có cạnh hẻm và cách ranh hơn 15 m, được gắn cờ nghi đầu cụt. Mẫu khảo sát gồm 12 điểm nghi đầu cụt và 12 điểm vào cụm có ít nhất hai đấu nối. Chưa loại nhánh dựa trên nhãn này.
5. Cụm hẻm là thành phần liên thông vô hướng của đồ thị chỉ gồm cạnh hẻm, bỏ các nút chắn khi phân cụm. Điểm đấu nối là nút OSM chung giữa một cạnh hẻm và cạnh thuộc một trong bốn trục. Chỉ tiêu cụm mô tả cấu trúc, khả năng đi theo chiều được đánh giá riêng. Lộ trình qua hẻm trong mẫu phải có một đoạn liên tục qua cạnh hẻm giữa hai đấu nối khác nhau và tuyến tìm được không lặp nút.
6. Chọn 24 cặp có hướng từ sáu tổ hợp giữa bốn trục, mỗi tổ hợp bốn cặp, hai cặp mỗi chiều. Hai đầu là nút OSM trên trục, cách nhau ít nhất 200 m theo đường thẳng. Chọn theo seed 20261109 trước khi chạy tìm đường. Mẫu mô tả thử nghiệm trên đồ thị, không đại diện cho mọi chuyến đi trong phường.
7. Chi phí là thời gian ước tính (giây) cộng số lần rẽ nhân mức phạt (giây tương đương). Giả định vận tốc 18 km/h trên bốn trục, 12 km/h trong hẻm và 15 km/h trên đường khác. Góc đổi hướng từ 35° tại điểm chuyển cạnh được tính một lần rẽ. Mức chính là 8 giây/lần, thử thêm 0 và 20. Trạng thái tìm kiếm là cạnh đến. A* dùng cận dưới bằng khoảng cách thẳng chia vận tốc lớn nhất. Hai thuật toán dùng cùng dữ liệu, quy tắc và trọng số. Mỗi thuật toán được đo 11 lần/cặp ở mức 8 giây, đảo thứ tự giữa các lượt. Thời gian xử lý tính bằng micro giây, không bao gồm đọc tệp và dựng đồ thị.

## Tệp kết quả

| Nội dung | Tệp |
| --- | --- |
| Dữ liệu nguồn, giữ nguyên ZIP OSM | `data/raw/Du_lieu_Thanh_My_Tay_OSM.zip` |
| Loại đường, lý do lọc, hạn chế rẽ | `kiem_tra_way_osm.csv`, `lam_sach.csv`, `han_che_re.csv` |
| Đồ thị, chuyển tiếp, đầu mút, mẫu thực địa | `canh_dinh_tuyen.geojson`, `chuyen_tiep.csv`, `dau_mut_hem.geojson`, `mau_doi_chieu.csv` |
| Cụm hẻm và điểm đấu nối | `cum_hem.csv`, `ket_noi_truc.csv`, `diem_noi.geojson` |
| Cặp điểm và tuyến mẫu qua hẻm | `cap_diem.csv`, `lo_trinh_qua_hem.csv`, `lo_trinh_qua_hem.geojson` |
| Thực nghiệm và độ nhạy | `so_sanh.csv`, `luot_do.csv`, `do_nhay.csv`, `lo_trinh.geojson` |
| Thống kê gộp, bản đồ, biểu đồ | `tong_hop.json`, thư mục `figures/` |
| Nhật ký có múi giờ UTC+07:00 | `logs/nhat_ky.tsv` |

Tệp dẫn xuất nằm trong `data/clean/`. CSV dùng UTF-8 BOM và dấu phẩy phân cột. Các trường thực địa để trống thể hiện chưa có quan sát. Chỉ tiêu thời gian hành trình là kết quả tính theo kịch bản, còn cột thời gian xử lý là đo trên máy chạy thuật toán.

## Chạy lại

Từ thư mục chứa các tệp Python, với Python 3.12:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python phan_tich.py
python kiem_chung.py
```

Chương trình đọc trực tiếp ZIP nguồn, viết bảng và hình mới, nối nhật ký vào cuối tệp. Kiểm chứng dùng NetworkX tính lại chi phí trên đồ thị chuyển tiếp, đối chiếu hình học trong ranh và kiểm tra từng cạnh của tuyến mẫu qua hẻm. Thời gian xử lý có thể thay đổi theo máy và tải hệ thống.

## Tải bản dữ liệu mới trực tiếp từ OSM

Cài các thư viện trong `requirements.txt` rồi chạy các lệnh dưới đây từ `Giai_doan_1/`.
Hai thư mục chỉ định trong ví dụ được tạo khi chạy.

```bash
python tai_du_lieu_osm.py --output-dir data/thu_thap_osm/lan_01
python phan_tich.py --archive data/thu_thap_osm/lan_01/Du_lieu_Thanh_My_Tay_OSM.zip --run-dir ket_qua_osm/lan_01
```

Script lấy relation 19260956 và mạng đường quanh ranh từ [OSM API 0.6](https://wiki.openstreetmap.org/wiki/API_v0.6). Script giữ hai phản hồi gốc, cắt lớp đường theo polygon và đóng gói PBF, GeoJSON, thông tin nguồn và mã SHA-256. PBF giữ các nút tham chiếu của đường được chọn và những relation hạn chế rẽ liên quan có trong phản hồi. Nhật ký `data/thu_thap_osm/lan_01/nhat_ky.tsv` ghi URL, giờ tải và số đối tượng xuất. Xem [nhật ký chạy kiểm tra](logs/kiem_tra_tai_osm.tsv) của lần tải ngày 09/11/2026.

Bản tải mới phản ánh trạng thái OSM vào lúc tải. Các số liệu trong báo cáo đã bàn giao được tính từ ZIP Geofabrik ngày 02/11/2026. Lệnh `python phan_tich.py` dùng ZIP Geofabrik đó theo mặc định. `kiem_chung.py` kiểm tra bộ kết quả gốc. Để tái lập kết quả từ một lần tải mới, lưu lại ZIP và thông tin nguồn của lần tải đó.

## Phần đánh giá còn mở

- RQ1 cần kết quả khảo sát tại 24 vị trí và đối chiếu biển/cổng để tính độ trùng khớp. Mục 6.2 của đề cương yêu cầu có ý kiến đồng ý của giảng viên trước khi khảo sát.
- Mốc triển khai này dùng 24 cặp theo khoảng 20–30 của Mục 3 và Mục 6.2. Phần tổng quan và ma trận của đề cương có nêu so sánh trên 30 cặp với ứng dụng dẫn đường thương mại. Kết quả hiện có là so sánh Dijkstra và A* trên bản đồ OSM. Chưa có phép đối chiếu ứng dụng thương mại, vận tốc giờ cao điểm hoặc thời gian hành trình đo thực tế.
