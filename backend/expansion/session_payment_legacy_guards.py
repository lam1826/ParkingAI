"""Frozen pre-session-credit online guards, recognized by the additive rollout."""

PRE_SESSION_CREDIT_ONLINE_GUARDS = {'trg_online_link_frozen': 'CREATE TRIGGER IF NOT EXISTS trg_online_link_frozen BEFORE UPDATE ON online_payment_links '
                           'WHEN NEW.id IS NOT OLD.id OR NEW.order_id IS NOT OLD.order_id OR NEW.site_id IS NOT '
                           'OLD.site_id OR NEW.channel IS NOT OLD.channel OR NEW.receiver_digest IS NOT '
                           'OLD.receiver_digest OR NEW.amount IS NOT OLD.amount OR NEW.currency IS NOT OLD.currency OR '
                           'NEW.description IS NOT OLD.description OR NEW.return_url IS NOT OLD.return_url OR '
                           'NEW.cancel_url IS NOT OLD.cancel_url OR NEW.expires_at IS NOT OLD.expires_at OR '
                           'NEW.created_at IS NOT OLD.created_at OR (OLD.payment_link_id IS NOT NULL AND '
                           'NEW.payment_link_id IS NOT OLD.payment_link_id) OR (OLD.settled_reference IS NOT NULL AND '
                           'NEW.settled_reference IS NOT OLD.settled_reference) OR (OLD.receipt_id IS NOT NULL AND '
                           "NEW.receipt_id IS NOT OLD.receipt_id) BEGIN SELECT RAISE(ABORT,'online payment identity is "
                           "immutable'); END",
 'trg_online_link_delete': 'CREATE TRIGGER IF NOT EXISTS trg_online_link_delete BEFORE DELETE ON online_payment_links '
                           "BEGIN SELECT RAISE(ABORT,'online payment identity must be retained'); END",
 'trg_online_link_replace': 'CREATE TRIGGER IF NOT EXISTS trg_online_link_replace BEFORE INSERT ON '
                            'online_payment_links WHEN EXISTS (SELECT 1 FROM online_payment_links WHERE id=NEW.id OR '
                            'order_id=NEW.order_id OR (payment_link_id IS NOT NULL AND '
                            "payment_link_id=NEW.payment_link_id)) BEGIN SELECT RAISE(ABORT,'online payment identity "
                            "cannot be replaced'); END",
 'trg_online_link_source': 'CREATE TRIGGER IF NOT EXISTS trg_online_link_source BEFORE INSERT ON online_payment_links '
                           'WHEN NOT EXISTS (SELECT 1 FROM portal_orders o WHERE o.id=NEW.order_id AND '
                           "o.payment_mode='payos' AND o.status='pending' AND o.site_id=NEW.site_id AND "
                           "o.amount=NEW.amount AND NEW.currency='VND' AND o.expires_at=NEW.expires_at) BEGIN SELECT "
                           "RAISE(ABORT,'online payment source mismatch'); END",
 'trg_online_link_receipt': 'CREATE TRIGGER IF NOT EXISTS trg_online_link_receipt BEFORE UPDATE ON '
                            'online_payment_links WHEN NEW.receipt_id IS NOT NULL AND (NEW.settled_reference IS NULL '
                            'OR NOT EXISTS (SELECT 1 FROM portal_orders o JOIN payments p ON p.id=o.receipt_id WHERE '
                            'o.id=NEW.order_id AND o.receipt_id=NEW.receipt_id AND o.status IN '
                            "('fulfilled','refunded') AND p.method='transfer' AND p.collected_by_id IS NULL AND "
                            "p.amount=NEW.amount)) BEGIN SELECT RAISE(ABORT,'online payment receipt mismatch'); END",
 'trg_online_inbox_update': 'CREATE TRIGGER IF NOT EXISTS trg_online_inbox_update BEFORE UPDATE ON '
                            "online_payment_inbox BEGIN SELECT RAISE(ABORT,'online payment evidence is immutable'); "
                            'END',
 'trg_online_inbox_delete': 'CREATE TRIGGER IF NOT EXISTS trg_online_inbox_delete BEFORE DELETE ON '
                            "online_payment_inbox BEGIN SELECT RAISE(ABORT,'online payment evidence must be "
                            "retained'); END",
 'trg_online_inbox_replace': 'CREATE TRIGGER IF NOT EXISTS trg_online_inbox_replace BEFORE INSERT ON '
                             'online_payment_inbox WHEN EXISTS (SELECT 1 FROM online_payment_inbox WHERE id=NEW.id OR '
                             '(channel=NEW.channel AND reference=NEW.reference AND payload_digest=NEW.payload_digest)) '
                             "BEGIN SELECT RAISE(ABORT,'online payment evidence cannot be replaced'); END",
 'trg_online_order_delete': 'CREATE TRIGGER IF NOT EXISTS trg_online_order_delete BEFORE DELETE ON portal_orders WHEN '
                            'EXISTS (SELECT 1 FROM online_payment_links WHERE order_id=OLD.id) BEGIN SELECT '
                            "RAISE(ABORT,'online payment order must be retained'); END",
 'trg_online_order_replace': 'CREATE TRIGGER IF NOT EXISTS trg_online_order_replace BEFORE INSERT ON portal_orders '
                             'WHEN EXISTS (SELECT 1 FROM online_payment_links WHERE order_id=NEW.id) BEGIN SELECT '
                             "RAISE(ABORT,'online payment order cannot be replaced'); END",
 'trg_online_processing_delete': 'CREATE TRIGGER IF NOT EXISTS trg_online_processing_delete BEFORE DELETE ON '
                                 "online_payment_processing BEGIN SELECT RAISE(ABORT,'online payment processing must "
                                 "be retained'); END",
 'trg_online_processing_replace': 'CREATE TRIGGER IF NOT EXISTS trg_online_processing_replace BEFORE INSERT ON '
                                  'online_payment_processing WHEN EXISTS (SELECT 1 FROM online_payment_processing '
                                  "WHERE id=NEW.id) BEGIN SELECT RAISE(ABORT,'online payment processing cannot be "
                                  "replaced'); END",
 'trg_online_processing_terminal': 'CREATE TRIGGER IF NOT EXISTS trg_online_processing_terminal BEFORE UPDATE ON '
                                   "online_payment_processing WHEN NEW.id IS NOT OLD.id OR (OLD.status!='received' AND "
                                   '(NEW.status IS NOT OLD.status OR NEW.reason IS NOT OLD.reason OR NEW.receipt_id IS '
                                   'NOT OLD.receipt_id OR NEW.processed_at IS NOT OLD.processed_at)) BEGIN SELECT '
                                   "RAISE(ABORT,'online processing decision is final'); END",
 'trg_online_review_update': 'CREATE TRIGGER IF NOT EXISTS trg_online_review_update BEFORE UPDATE ON '
                             "online_payment_review_decisions BEGIN SELECT RAISE(ABORT,'online review decision is "
                             "immutable'); END",
 'trg_online_review_delete': 'CREATE TRIGGER IF NOT EXISTS trg_online_review_delete BEFORE DELETE ON '
                             "online_payment_review_decisions BEGIN SELECT RAISE(ABORT,'online review decision must be "
                             "retained'); END",
 'trg_online_review_replace': 'CREATE TRIGGER IF NOT EXISTS trg_online_review_replace BEFORE INSERT ON '
                              'online_payment_review_decisions WHEN EXISTS (SELECT 1 FROM '
                              'online_payment_review_decisions WHERE id=NEW.id OR (inbox_id=NEW.inbox_id AND '
                              "request_id=NEW.request_id) OR (action='confirmed_external_refund' AND "
                              "NEW.action='confirmed_external_refund' AND channel=NEW.channel AND "
                              "payment_reference=NEW.payment_reference)) BEGIN SELECT RAISE(ABORT,'online review "
                              "decision cannot be replaced'); END",
 'trg_online_review_source': 'CREATE TRIGGER IF NOT EXISTS trg_online_review_source BEFORE INSERT ON '
                             'online_payment_review_decisions WHEN NOT EXISTS (SELECT 1 FROM online_payment_inbox i '
                             'JOIN online_payment_processing p ON p.id=i.id WHERE i.id=NEW.inbox_id AND '
                             "p.status='review' AND i.channel=NEW.channel AND i.reference=NEW.payment_reference AND "
                             "(NEW.action='note' OR (NEW.refund_amount=i.amount AND i.currency='VND' AND "
                             '(i.verification_issue IS NULL OR i.verification_issue NOT IN '
                             "('account_mismatch','currency_mismatch')) AND NOT EXISTS (SELECT 1 FROM "
                             'online_payment_links l WHERE l.channel=i.channel AND l.settled_reference=i.reference)))) '
                             "BEGIN SELECT RAISE(ABORT,'online review source mismatch'); END",
 'trg_online_inbox_integer': 'CREATE TRIGGER IF NOT EXISTS trg_online_inbox_integer BEFORE INSERT ON '
                             "online_payment_inbox WHEN typeof(NEW.amount)!='integer' OR "
                             "typeof(NEW.order_code)!='integer' BEGIN SELECT RAISE(ABORT,'online evidence requires "
                             "integer money and identity'); END",
 'trg_online_processing_receipt': 'CREATE TRIGGER IF NOT EXISTS trg_online_processing_receipt BEFORE UPDATE ON '
                                  "online_payment_processing WHEN NEW.status IN ('processed','duplicate') AND NOT "
                                  'EXISTS (SELECT 1 FROM online_payment_inbox i JOIN online_payment_links l ON '
                                  'l.id=i.link_id WHERE i.id=NEW.id AND l.receipt_id=NEW.receipt_id AND '
                                  'l.settled_reference=i.reference AND l.channel=i.channel AND l.id=i.order_code AND '
                                  'l.amount=i.amount AND l.currency=i.currency AND l.receiver_digest=i.receiver_digest '
                                  "AND l.payment_link_id=i.payment_link_id) BEGIN SELECT RAISE(ABORT,'online "
                                  "processing receipt mismatch'); END"}
