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
