"""Cac bang cua CSDL data_scam."""
from flask_login import UserMixin
from sqlalchemy import UniqueConstraint, CheckConstraint, Index
from werkzeug.security import check_password_hash, generate_password_hash

from .database import db, utcnow

AVATAR_COLORS = ["#1b74e4", "#e4572e", "#7b3fe4", "#2e9e5b", "#d6336c", "#f08c00", "#0b7285", "#5f3dc4"]


class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    # Moi mo hinh AI co "the gioi" tai khoan rieng: cung ten van tao duoc o mo hinh khac.
    model_key = db.Column(db.String(20), nullable=False, default="svm")
    username = db.Column(db.String(30), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    avatar_color = db.Column(db.String(9), nullable=False, default="#1b74e4")
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    last_seen_at = db.Column(db.DateTime, nullable=True)
    # ---- ho so ----
    display_name = db.Column(db.String(80), nullable=False, default="")
    search_name = db.Column(db.String(200), nullable=False, default="")      # ten khong dau, chu thuong (tim kiem)
    bio = db.Column(db.String(300), nullable=True)
    birth_year = db.Column(db.SmallInteger, nullable=True)
    avatar_path = db.Column(db.String(255), nullable=True)                    # ten file trong static/uploads/avatars
    cover_path = db.Column(db.String(255), nullable=True)
    # ---- xac minh (gia lap) ----
    phone = db.Column(db.String(20), nullable=True)
    phone_verified = db.Column(db.Boolean, nullable=False, default=False)
    identity_verified = db.Column(db.Boolean, nullable=False, default=False)
    # ---- cai dat ----
    dark_mode = db.Column(db.Boolean, nullable=False, default=False)
    agent3_enabled = db.Column(db.Boolean, nullable=False, default=True)      # AI 3 doc vi (quet tin nhan)
    family_question = db.Column(db.String(200), nullable=True)                # mat ma gia dinh
    family_answer_hash = db.Column(db.String(255), nullable=True)
    guardian_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    is_demo = db.Column(db.Boolean, nullable=False, default=False)            # tai khoan demo (dang nhap nhanh)

    guardian = db.relationship("User", remote_side=[id], foreign_keys=[guardian_id])
    __table_args__ = (UniqueConstraint("model_key", "username", name="uq_user_model_username"),)

    @property
    def name(self) -> str:
        return self.display_name or self.username

    def set_password(self, raw: str):
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw: str) -> bool:
        return check_password_hash(self.password_hash, raw)


class FriendRequest(db.Model):
    """Loi moi ket ban. status: pending -> accepted | declined. Ban be = ban ghi accepted."""
    __tablename__ = "friend_requests"
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    status = db.Column(db.String(10), nullable=False, default="pending")
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    responded_at = db.Column(db.DateTime, nullable=True)

    sender = db.relationship("User", foreign_keys=[sender_id])
    receiver = db.relationship("User", foreign_keys=[receiver_id])
    __table_args__ = (
        UniqueConstraint("sender_id", "receiver_id", name="uq_friend_request_pair"),
        CheckConstraint("sender_id <> receiver_id", name="ck_friend_request_not_self"),
        Index("ix_friend_requests_receiver_status", "receiver_id", "status"),
    )


class Block(db.Model):
    __tablename__ = "blocks"
    id = db.Column(db.Integer, primary_key=True)
    blocker_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    blocked_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    # user = nguoi dung tu chan | guardian = Ve si tu dong chan sau 3 lan phat hien lua dao (chi go qua Khieu nai)
    source = db.Column(db.String(10), nullable=False, default="user")
    reason = db.Column(db.String(300), nullable=True)

    blocked = db.relationship("User", foreign_keys=[blocked_id])
    __table_args__ = (UniqueConstraint("blocker_id", "blocked_id", name="uq_block_pair"),)


class Conversation(db.Model):
    """Cuoc chat 1-1. user_low_id < user_high_id de moi cap chi co 1 cuoc chat."""
    __tablename__ = "conversations"
    id = db.Column(db.Integer, primary_key=True)
    user_low_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    user_high_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    last_message_at = db.Column(db.DateTime, nullable=True)

    user_low = db.relationship("User", foreign_keys=[user_low_id])
    user_high = db.relationship("User", foreign_keys=[user_high_id])
    __table_args__ = (
        UniqueConstraint("user_low_id", "user_high_id", name="uq_conversation_pair"),
        CheckConstraint("user_low_id < user_high_id", name="ck_conversation_order"),
    )

    def other_user_id(self, me_id: int) -> int:
        return self.user_high_id if me_id == self.user_low_id else self.user_low_id

    def has_user(self, uid: int) -> bool:
        return uid in (self.user_low_id, self.user_high_id)


class Message(db.Model):
    __tablename__ = "messages"
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    kind = db.Column(db.String(10), nullable=False, default="text")          # text | image | file | voice | call
    body = db.Column(db.Text, nullable=True)
    attachment_path = db.Column(db.String(255), nullable=True)               # ten file da luu trong uploads/
    attachment_name = db.Column(db.String(255), nullable=True)               # ten file goc
    attachment_mime = db.Column(db.String(100), nullable=True)
    attachment_size = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    delivered_at = db.Column(db.DateTime, nullable=True)
    read_at = db.Column(db.DateTime, nullable=True)
    # ---- ket qua kiem duyet cua AI (CHI nguoi nhan duoc thay) ----
    ai_checked = db.Column(db.Boolean, nullable=False, default=False)
    ai_model = db.Column(db.String(20), nullable=True)
    ai_score = db.Column(db.Float, nullable=True)
    ai_flagged = db.Column(db.Boolean, nullable=False, default=False)
    warning_level = db.Column(db.SmallInteger, nullable=False, default=0)    # 0 | 1 | 2 | 3
    # ---- Ve si (chay nen sau khi tin da gui) ----
    scan_status = db.Column(db.String(10), nullable=False, default="none")   # none | pending | done | off
    attachment_meta = db.Column(db.JSON, nullable=True)                       # tin thoai: {"duration": giay, "masked": bool}
    call_id = db.Column(db.Integer, nullable=True)                            # tin "nhat ky cuoc goi"
    # ---- tinh nang chat ----
    reply_to_id = db.Column(db.Integer, db.ForeignKey("messages.id", ondelete="SET NULL"), nullable=True)   # tra loi trich dan
    recalled_at = db.Column(db.DateTime, nullable=True)                       # thu hoi (noi dung an voi CA 2 ben)
    pinned_at = db.Column(db.DateTime, nullable=True)                         # ghim len dau cuoc chat
    pinned_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    # ---- truy vet: IP / trinh duyet nguoi gui luc gui tin (CHI quan tri vien xem; tu xoa sau IP_RETENTION_DAYS) ----
    sender_ip = db.Column(db.String(45), nullable=True)
    sender_user_agent = db.Column(db.String(255), nullable=True)

    conversation = db.relationship("Conversation", backref=db.backref("messages", lazy="dynamic",
                                                                       cascade="all, delete-orphan"))
    sender = db.relationship("User", foreign_keys=[sender_id])
    reply_to = db.relationship("Message", remote_side=[id], foreign_keys=[reply_to_id])
    __table_args__ = (Index("ix_messages_conv_id", "conversation_id", "id"),
                      Index("ix_messages_unread", "conversation_id", "sender_id", "read_at"),
                      Index("ix_messages_pinned", "conversation_id", "pinned_at"))


class MessageReaction(db.Model):
    """Tha cam xuc len tin nhan: moi nguoi 1 cam xuc / tin (bam lai cung cam xuc = go)."""
    __tablename__ = "message_reactions"
    message_id = db.Column(db.Integer, db.ForeignKey("messages.id", ondelete="CASCADE"), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    emoji = db.Column(db.String(16), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


class ScamCounter(db.Model):
    """So tin bi AI gan co cua MOI nguoi gui trong TUNG cuoc chat (cong don, khong reset)."""
    __tablename__ = "scam_counters"
    conversation_id = db.Column(db.Integer, db.ForeignKey("conversations.id", ondelete="CASCADE"), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    flagged_count = db.Column(db.Integer, nullable=False, default=0)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class FeedAuthor(db.Model):
    """Tai khoan GIA chi dung cho bang tin (khong dang nhap duoc)."""
    __tablename__ = "feed_authors"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    avatar_color = db.Column(db.String(9), nullable=False)
    bio = db.Column(db.String(120), nullable=True)


class FeedPost(db.Model):
    __tablename__ = "feed_posts"
    id = db.Column(db.Integer, primary_key=True)
    author_id = db.Column(db.Integer, db.ForeignKey("feed_authors.id", ondelete="CASCADE"), nullable=False)
    content = db.Column(db.Text, nullable=False)
    image = db.Column(db.String(200), nullable=True)
    likes = db.Column(db.Integer, nullable=False, default=0)
    comments = db.Column(db.Integer, nullable=False, default=0)
    shares = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    author = db.relationship("FeedAuthor")
    __table_args__ = (Index("ix_feed_posts_created", "created_at"),)


# =========================================================================== #
# Ho so: lich su doi ten / doi anh
# =========================================================================== #
class NameHistory(db.Model):
    __tablename__ = "name_history"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    old_name = db.Column(db.String(80), nullable=False)
    new_name = db.Column(db.String(80), nullable=False)
    changed_at = db.Column(db.DateTime, nullable=False, default=utcnow)


class AvatarHistory(db.Model):
    __tablename__ = "avatar_history"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    path = db.Column(db.String(255), nullable=False)
    changed_at = db.Column(db.DateTime, nullable=False, default=utcnow)


class FamilyMember(db.Model):
    """Danh sach nguoi than (dung cho Mat ma gia dinh)."""
    __tablename__ = "family_members"
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    relation = db.Column(db.String(40), nullable=True)

    member = db.relationship("User", foreign_keys=[member_id])


# =========================================================================== #
# Bang tin that (song song voi bang tin gia FeedPost)
# =========================================================================== #
class Post(db.Model):
    __tablename__ = "posts"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    body = db.Column(db.Text, nullable=True)
    image_path = db.Column(db.String(255), nullable=True)                     # static/uploads/posts/...
    shared_post_id = db.Column(db.Integer, db.ForeignKey("posts.id", ondelete="SET NULL"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    author = db.relationship("User")
    shared = db.relationship("Post", remote_side=[id])
    __table_args__ = (Index("ix_posts_created", "created_at"), Index("ix_posts_user", "user_id", "created_at"))


class PostReaction(db.Model):
    __tablename__ = "post_reactions"
    post_id = db.Column(db.Integer, db.ForeignKey("posts.id", ondelete="CASCADE"), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    kind = db.Column(db.String(10), nullable=False)                           # like | love | haha | sad | angry
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


class PostComment(db.Model):
    __tablename__ = "post_comments"
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey("posts.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    author = db.relationship("User")


# =========================================================================== #
# Thong bao, bao cao, phan hoi (nhan de train)
# =========================================================================== #
class Notification(db.Model):
    __tablename__ = "notifications"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    # friend_request | friend_accept | comment | reaction | share | scam_alert | guardian | guardian_block | appeal | call
    kind = db.Column(db.String(30), nullable=False)
    text = db.Column(db.String(400), nullable=False)
    link = db.Column(db.String(255), nullable=True)
    level = db.Column(db.SmallInteger, nullable=False, default=0)
    read_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    actor = db.relationship("User", foreign_keys=[actor_id])
    __table_args__ = (Index("ix_notifications_user", "user_id", "id"),)


class Report(db.Model):
    """Bao cao lua dao (nguoi dung bam 'Bao cao'): chi luu lai lam nhan train, KHONG canh bao ai khac."""
    __tablename__ = "reports"
    id = db.Column(db.Integer, primary_key=True)
    reporter_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    reported_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    message_id = db.Column(db.Integer, db.ForeignKey("messages.id", ondelete="SET NULL"), nullable=True)
    source = db.Column(db.String(20), nullable=False, default="user")         # user
    reason = db.Column(db.String(300), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


class Feedback(db.Model):
    """'Khong phai lua dao' / 'Day la nguoi quen' / 'Bao cao' -> nhan de train mo hinh kich ban sau nay."""
    __tablename__ = "feedback"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    target_user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    message_id = db.Column(db.Integer, db.ForeignKey("messages.id", ondelete="SET NULL"), nullable=True)
    label = db.Column(db.String(20), nullable=False)                          # not_scam | acquaintance | scam
    text = db.Column(db.Text, nullable=True)                                  # noi dung tin (lam nhan train)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


# =========================================================================== #
# Cuoc goi thoai / video 1-1 (WebRTC)
# =========================================================================== #
class Call(db.Model):
    __tablename__ = "calls"
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    caller_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    callee_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    video = db.Column(db.Boolean, nullable=False, default=True)
    status = db.Column(db.String(12), nullable=False, default="ringing")      # ringing | active | ended | declined | missed
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    answered_at = db.Column(db.DateTime, nullable=True)
    ended_at = db.Column(db.DateTime, nullable=True)

    caller = db.relationship("User", foreign_keys=[caller_id])
    callee = db.relationship("User", foreign_keys=[callee_id])
    __table_args__ = (Index("ix_calls_pair", "caller_id", "callee_id", "created_at"),)


# =========================================================================== #
# Nhat ky Ve si: moi su kien (tin nhan / hoi ve si / khieu nai)
# =========================================================================== #
class GuardianEvent(db.Model):
    __tablename__ = "guardian_events"
    id = db.Column(db.Integer, primary_key=True)
    model_key = db.Column(db.String(20), nullable=False)
    kind = db.Column(db.String(20), nullable=False)          # message | ask | appeal
    protected_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=True)   # nguoi duoc bao ve
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=True)       # nguoi bi xem xet
    message_id = db.Column(db.Integer, db.ForeignKey("messages.id", ondelete="SET NULL"), nullable=True)
    level = db.Column(db.SmallInteger, nullable=False, default=0)
    agent3_called = db.Column(db.Boolean, nullable=False, default=False)
    results = db.Column(db.JSON, nullable=True)              # {text, agent3, decision}
    timings = db.Column(db.JSON, nullable=True)              # ms tung buoc
    modes = db.Column(db.JSON, nullable=True)                # che do tung agent
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    protected = db.relationship("User", foreign_keys=[protected_id])
    actor = db.relationship("User", foreign_keys=[actor_id])
    __table_args__ = (Index("ix_guardian_events_model", "model_key", "id"),)


# =========================================================================== #
# Khieu nai go chan (sau khi Ve si tu dong chan): chup anh truc tiep + Mat ma gia dinh + 2 ben xac nhan
# =========================================================================== #
class Appeal(db.Model):
    __tablename__ = "appeals"
    id = db.Column(db.Integer, primary_key=True)
    protected_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)   # nguoi duoc bao ve (ben chan)
    accused_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)     # nguoi bi chan
    conversation_id = db.Column(db.Integer, db.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=True)
    opened_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    status = db.Column(db.String(10), nullable=False, default="open")       # open | success | failed | expired
    fail_reason = db.Column(db.String(300), nullable=True)
    question_required = db.Column(db.Boolean, nullable=False, default=False)  # nguoi duoc bao ve co Mat ma gia dinh
    question_attempts = db.Column(db.SmallInteger, nullable=False, default=0)
    question_passed = db.Column(db.Boolean, nullable=False, default=False)
    protected_confirm = db.Column(db.Boolean, nullable=True)               # None = chua tra loi
    accused_confirm = db.Column(db.Boolean, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    closed_at = db.Column(db.DateTime, nullable=True)

    protected = db.relationship("User", foreign_keys=[protected_id])
    accused = db.relationship("User", foreign_keys=[accused_id])
    __table_args__ = (Index("ix_appeals_pair", "protected_id", "accused_id", "status"),)


class AppealCapture(db.Model):
    """Mot lan chup truc tiep (3 khung) cua 1 ben. Anh luu tam trong uploads/appeals, XOA khi khieu nai ket thuc."""
    __tablename__ = "appeal_captures"
    id = db.Column(db.Integer, primary_key=True)
    appeal_id = db.Column(db.Integer, db.ForeignKey("appeals.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    action = db.Column(db.String(120), nullable=False)                     # thao tac ngau nhien da yeu cau
    files = db.Column(db.JSON, nullable=True)                               # ten file anh (None sau khi xoa)
    faces_found = db.Column(db.SmallInteger, nullable=False, default=0)
    motion = db.Column(db.Float, nullable=False, default=0)                # do chuyen dong giua cac khung (chong gio anh)
    passed = db.Column(db.Boolean, nullable=False, default=False)
    reason = db.Column(db.String(300), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


# =========================================================================== #
# Truy vet IP ke lua dao (chi quan tri vien xem; nan nhan xem phan cua minh khi yeu cau duoc duyet)
# =========================================================================== #
class LoginLog(db.Model):
    """IP moi lan dang nhap. Tu xoa sau IP_RETENTION_DAYS."""
    __tablename__ = "login_logs"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    ip = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    __table_args__ = (Index("ix_login_logs_user", "user_id", "id"), Index("ix_login_logs_created", "created_at"))


class ScamTrace(db.Model):
    """Ho so truy vet tao khi Ve si TU DONG CHAN (lan 3). Giu lau dai; luu ban sao ten de con dung khi tai khoan bi xoa."""
    __tablename__ = "scam_traces"
    id = db.Column(db.Integer, primary_key=True)
    model_key = db.Column(db.String(20), nullable=False, default="svm")
    offender_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    victim_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True)
    offender_username = db.Column(db.String(30), nullable=False)
    offender_name = db.Column(db.String(80), nullable=False)
    victim_username = db.Column(db.String(30), nullable=False)
    victim_name = db.Column(db.String(80), nullable=False)
    block_nth = db.Column(db.SmallInteger, nullable=False, default=1)       # lan chan thu N (vong lap khieu nai)
    # IP chinh = IP cua tin lua dao lan 3 (hoac IP dang nhap gan nhat neu tin khong co IP)
    ip = db.Column(db.String(45), nullable=True, index=True)
    user_agent = db.Column(db.String(255), nullable=True)
    country = db.Column(db.String(80), nullable=True)
    region = db.Column(db.String(120), nullable=True)
    city = db.Column(db.String(120), nullable=True)
    isp = db.Column(db.String(160), nullable=True)
    geo_source = db.Column(db.String(10), nullable=False, default="unknown")   # demo | private | mmdb | online | unknown
    evidence = db.Column(db.JSON, nullable=True)                 # {"messages": [...], "logins": [...], "ips": [...]}
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    offender = db.relationship("User", foreign_keys=[offender_id])
    victim = db.relationship("User", foreign_keys=[victim_id])
    __table_args__ = (Index("ix_scam_traces_model", "model_key", "id"),)


class TraceRequest(db.Model):
    """Nan nhan xin xem thong tin truy vet -> quan tri vien duyet / tu choi."""
    __tablename__ = "trace_requests"
    id = db.Column(db.Integer, primary_key=True)
    trace_id = db.Column(db.Integer, db.ForeignKey("scam_traces.id", ondelete="CASCADE"), nullable=False, index=True)
    requester_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    reason = db.Column(db.String(500), nullable=False)
    status = db.Column(db.String(10), nullable=False, default="pending")    # pending | approved | rejected
    admin_note = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    resolved_at = db.Column(db.DateTime, nullable=True)

    trace = db.relationship("ScamTrace")
    requester = db.relationship("User", foreign_keys=[requester_id])
    __table_args__ = (Index("ix_trace_requests_status", "status", "id"),)
