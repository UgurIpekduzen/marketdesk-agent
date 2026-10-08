"""Every Turkish string shown to the end user."""

# The same sentence for an order that does not exist and for one that
# belongs to another customer.
ORDER_NOT_FOUND = "Bu numarayla size ait bir sipariş bulunamadı."

INVALID_ORDER_STATUS = "Geçersiz sipariş durumu. Geçerli değerler: {allowed}."
INVALID_RETURN_REASON = "Geçersiz iade nedeni. Geçerli değerler: {allowed}."

INVALID_AMOUNT = "Geçersiz iade tutarı."
AMOUNT_MISMATCH = "İade tutarı, bu sipariş için hesaplanan tutarla uyuşmuyor."
RETURN_NOT_POSSIBLE = "Bu sipariş için şu anda iade talebi açılamıyor."
DUPLICATE_REQUEST = (
    "Bu sipariş için daha önce bir iade talebi açılmış; ikinci bir talep açılamaz."
)
APPROVAL_REQUIRED = (
    "İade talebi ancak sizin onayınızla oluşturulur. Henüz hiçbir kayıt açılmadı."
)
RETURN_REQUEST_CREATED = "İade talebiniz oluşturuldu."

INVALID_PRIORITY = "Geçersiz öncelik. Geçerli değerler: {allowed}."
EMPTY_SUMMARY = "Devir özeti boş olamaz."
ESCALATED = "Konu bir müşteri temsilcisine iletildi."

UNKNOWN_METRIC = "Böyle bir metrik tanımlı değil. Tanımlı metrikler: {allowed}."
INVALID_DIMENSION = (
    "Bu metrik {name} boyutuna göre kırılamaz. İzinli boyutlar: {allowed}."
)
TOO_MANY_DIMENSIONS = "Bir metrik en fazla {limit} farklı boyuta göre kırılabilir."
ITEM_DIMENSIONS_TOGETHER = (
    "Bu metrik {names} boyutlarına aynı anda kırılamaz: aynı sipariş birden "
    "fazla kez sayılır. Boyutlardan birini seçin."
)
INVALID_METRIC_FILTER = (
    "Bu metrik {name} ile filtrelenemez. İzinli filtreler: {allowed}."
)
INVALID_FILTER_VALUE = (
    "{name} filtresinin değeri bir metin ya da metin listesi olmalıdır."
)
INVALID_PERIOD_FILTER = "{name} filtresi YYYY-AA-GG biçiminde bir tarih olmalıdır."

SQL_REJECTED = {
    "EMPTY_QUERY": "Sorgu boş.",
    "PARSE_ERROR": "Sorgu ayrıştırılamadı; SQL yazımını kontrol edin.",
    "MULTIPLE_STATEMENTS": "Tek seferde yalnızca bir SQL ifadesi çalıştırılabilir.",
    "NOT_A_SELECT": "Yalnızca SELECT sorguları çalıştırılabilir.",
    "FORBIDDEN_STATEMENT": (
        "Sorgu izin verilmeyen bir ifade içeriyor; yalnızca veri okunabilir."
    ),
    "TABLE_NOT_ALLOWED": (
        "Sorgu izin verilmeyen bir tabloya erişiyor. İzinli görünümler: {allowed}."
    ),
    "FUNCTION_NOT_ALLOWED": "Sorgu izin verilmeyen bir fonksiyon çağırıyor.",
}
SQL_ERROR = "Sorgu çalıştırılamadı."
SQL_TIMEOUT = "Sorgu {seconds} saniyede tamamlanmadığı için durduruldu."

# How a policy section is cited in an answer.
POLICY_CITATION = "{document}, Bölüm {number}"
EMPTY_POLICY_QUERY = "Arama metni boş olamaz."

# --- Support agent ------------------------------------------------------

STEP_LIMIT_REACHED = (
    "İsteğinizi bu adımda tamamlayamadım. Sorunuzu biraz daha açık yazabilir "
    "ya da konunun bir müşteri temsilcisine aktarılmasını isteyebilirsiniz."
)
EMPTY_REPLY = "Şu anda bir cevap oluşturamadım. Lütfen sorunuzu yeniden yazın."

RETURN_REASON_LABELS = {
    "changed_mind": "vazgeçme",
    "late": "geç teslim",
    "damaged": "hasarlı ürün",
    "wrong_item": "yanlış ürün",
}
REQUEST_STATUS_LABELS = {
    "PENDING_REVIEW": "inceleme bekliyor",
    "PENDING_SENIOR": "kıdemli onay bekliyor",
}
APPROVAL_SUMMARY = (
    "Oluşturulacak iade talebi:\n"
    "  Sipariş: {order}\n"
    "  İade nedeni: {reason}\n"
    "  İade tutarı: {amount} BRL\n"
    "  Talep şu durumda açılacak: {status}"
)
APPROVAL_QUESTION = "Onaylıyor musunuz? [e/h] "
RETURN_REQUEST_CREATED_DETAIL = (
    "İade talebiniz oluşturuldu. Talep numarası: {request_id}, durum: {status}."
)
RETURN_REQUEST_NOT_CREATED = "İade talebi oluşturulmadı: {reason}"
APPROVAL_DECLINED = "Onay vermediniz; iade talebi oluşturulmadı."

# --- Chat command -------------------------------------------------------

CHAT_BANNER = "MarketDesk müşteri desteği. Çıkmak için 'çık' yazın.\nSorunuzu yazın:"
CHAT_PROMPT = "> "
CHAT_GOODBYE = "Görüşmek üzere."
CHAT_UNKNOWN_CUSTOMER = "Bu müşteri için kayıtlı sipariş bulunamadı."
