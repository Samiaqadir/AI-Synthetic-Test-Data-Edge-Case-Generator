-- Samia Synthetic Data Generation Output
-- Topologically ordered INSERT statements
BEGIN TRANSACTION;

-- Table: users (10 records)
INSERT INTO "users" ("id", "username", "email", "full_name", "age", "is_active", "created_at") VALUES (1, 'johnsonjoshua', 'donaldgarcia@example.com', 'garzaanthony', 44, True, '2025-01-25T15:41:44.897538');
INSERT INTO "users" ("id", "username", "email", "full_name", "age", "is_active", "created_at") VALUES (2, 'williamjohnson', 'jennifermiles@example.com', 'lrobinson', 36, True, '2025-06-09T10:10:54.474576');
INSERT INTO "users" ("id", "username", "email", "full_name", "age", "is_active", "created_at") VALUES (3, 'blakeerik', 'jpeterson@example.com', 'susanrogers', 32, True, '2025-01-24T23:03:05.189289');
INSERT INTO "users" ("id", "username", "email", "full_name", "age", "is_active", "created_at") VALUES (4, 'howardmaurice', 'lindsay78@apex-cloud.io', 'dudleynicholas', 33, True, '2025-12-26T11:11:13.924725');
INSERT INTO "users" ("id", "username", "email", "full_name", "age", "is_active", "created_at") VALUES (5, 'barbara10', 'kendragalloway@example.com', 'michellejames', 18, True, '2025-10-15T10:02:51.423042');
INSERT INTO "users" ("id", "username", "email", "full_name", "age", "is_active", "created_at") VALUES (6, 'francisco53', 'jacqueline19@lumina-retail.com', 'amandasanchez', 27, True, '2025-10-21T21:11:59.937379');
INSERT INTO "users" ("id", "username", "email", "full_name", "age", "is_active", "created_at") VALUES (7, 'veronica83', 'megan03@techpulse.net', 'trujillorichard', 35, False, '2025-01-05T13:27:45.681738');
INSERT INTO "users" ("id", "username", "email", "full_name", "age", "is_active", "created_at") VALUES (8, 'jason76', 'ithomas@lumina-retail.com', 'julieryan', 33, True, '2026-05-17T21:21:48.285328');
INSERT INTO "users" ("id", "username", "email", "full_name", "age", "is_active", "created_at") VALUES (9, 'zhurst', 'jeffrey28@apex-cloud.io', 'ddavis', 39, True, '2026-08-09T05:31:07.378366');
INSERT INTO "users" ("id", "username", "email", "full_name", "age", "is_active", "created_at") VALUES (10, 'courtneyconner', 'ycarlson@lumina-retail.com', 'dcarlson', 54, True, '2025-12-09T17:15:16.404213');

-- Table: categories (10 records)
INSERT INTO "categories" ("id", "name", "slug", "description") VALUES (1, 'Shannon Smith', 'Race Mr', 'Born itself law west then enjoy. Seven medical blood personal success medical current.');
INSERT INTO "categories" ("id", "name", "slug", "description") VALUES (2, 'Christopher Ashley', 'Truth out major born guy', 'Around there water beat magazine. Within mouth call process.');
INSERT INTO "categories" ("id", "name", "slug", "description") VALUES (3, 'Carmen Rose', 'Institution deep much role cut', 'Yet practice just military building different. Again network open according remain arrive.');
INSERT INTO "categories" ("id", "name", "slug", "description") VALUES (4, 'Andre Rivera', 'Draw protect Democrat car very', 'Line six space couple best issue interest. Tell approach president position art rock song. Eat couple large instead.');
INSERT INTO "categories" ("id", "name", "slug", "description") VALUES (5, 'David Leblanc', 'Space task better present', 'Why unit support. Image loss ten total. Her world enter six.');
INSERT INTO "categories" ("id", "name", "slug", "description") VALUES (6, 'Jay Bernard', 'Product main couple design around', 'Security arm once me. Church whether bag control organization push dog. Walk now often always.');
INSERT INTO "categories" ("id", "name", "slug", "description") VALUES (7, 'Matthew Cunningham', 'Various daughter respond draw', 'Public feel first sell. Act perform none beyond. Defense enter value thing these hard citizen.');
INSERT INTO "categories" ("id", "name", "slug", "description") VALUES (8, 'Michele Carr', 'Account stage federal professional voice', 'Break blood network evening painting. Data plant enough major town suffer.');
INSERT INTO "categories" ("id", "name", "slug", "description") VALUES (9, 'Jeff Hill', 'Four capital', 'Scientist necessary into act. War real chance along.');
INSERT INTO "categories" ("id", "name", "slug", "description") VALUES (10, 'Juan Jordan', 'Final together', 'Decide economic bill sister this image.');

-- Table: orders (10 records)
INSERT INTO "orders" ("id", "user_id", "status", "total_amount", "shipping_address", "created_at") VALUES (1, 6, 'completed', 157.53, 'See understand door class son', '2025-03-27T13:04:22.816749');
INSERT INTO "orders" ("id", "user_id", "status", "total_amount", "shipping_address", "created_at") VALUES (2, 9, 'pending', 94.14, 'Agent say forward us', '2026-06-27T05:28:37.978725');
INSERT INTO "orders" ("id", "user_id", "status", "total_amount", "shipping_address", "created_at") VALUES (3, 9, 'completed', 108.32, 'Environment skin blue', '2026-08-17T07:29:06.832273');
INSERT INTO "orders" ("id", "user_id", "status", "total_amount", "shipping_address", "created_at") VALUES (4, 6, 'processing', 44.44, 'Develop staff least figure', '2026-06-22T04:41:28.891110');
INSERT INTO "orders" ("id", "user_id", "status", "total_amount", "shipping_address", "created_at") VALUES (5, 4, 'completed', 74.55, 'Development process huge', '2025-06-09T17:24:39.490990');
INSERT INTO "orders" ("id", "user_id", "status", "total_amount", "shipping_address", "created_at") VALUES (6, 8, 'completed', 16.15, 'Whom evidence', '2026-03-01T19:13:32.748124');
INSERT INTO "orders" ("id", "user_id", "status", "total_amount", "shipping_address", "created_at") VALUES (7, 5, 'pending', 39.67, 'Quickly such former agree', '2026-08-20T20:53:32.231899');
INSERT INTO "orders" ("id", "user_id", "status", "total_amount", "shipping_address", "created_at") VALUES (8, 4, 'processing', 30.85, 'Condition while enter', '2025-02-05T09:32:14.128364');
INSERT INTO "orders" ("id", "user_id", "status", "total_amount", "shipping_address", "created_at") VALUES (9, 9, 'processing', 166.05, 'Generation skill job worker', '2025-02-10T16:31:19.952253');
INSERT INTO "orders" ("id", "user_id", "status", "total_amount", "shipping_address", "created_at") VALUES (10, 1, 'processing', 28.64, 'Couple and job mind southern', '2026-04-03T22:43:32.309790');

-- Table: products (10 records)
INSERT INTO "products" ("id", "category_id", "title", "sku", "price", "stock_qty", "is_published", "created_at") VALUES (1, 10, 'Engineer, chemical', 'SKU-XBE-6155', 15.07, 8846, True, '2026-10-12T08:17:16.301865');
INSERT INTO "products" ("id", "category_id", "title", "sku", "price", "stock_qty", "is_published", "created_at") VALUES (2, 3, 'Lawyer', 'SKU-NUQ-5339', 40.91, 4284, True, '2026-07-30T16:04:21.598695');
INSERT INTO "products" ("id", "category_id", "title", "sku", "price", "stock_qty", "is_published", "created_at") VALUES (3, 6, 'Hydrologist', 'SKU-GTQ-4593', 31.93, 8611, True, '2025-09-12T12:49:27.403137');
INSERT INTO "products" ("id", "category_id", "title", "sku", "price", "stock_qty", "is_published", "created_at") VALUES (4, 3, 'Operational researcher', 'SKU-SSJ-7916', 41.06, 5959, True, '2025-02-19T04:37:27.941861');
INSERT INTO "products" ("id", "category_id", "title", "sku", "price", "stock_qty", "is_published", "created_at") VALUES (5, 5, 'Petroleum engineer', 'SKU-QYR-1188', 43.79, 8847, True, '2026-05-18T17:00:42.614820');
INSERT INTO "products" ("id", "category_id", "title", "sku", "price", "stock_qty", "is_published", "created_at") VALUES (6, 6, 'Ecologist', 'SKU-NKT-2827', 23.65, 33, True, '2025-09-10T20:11:26.793314');
INSERT INTO "products" ("id", "category_id", "title", "sku", "price", "stock_qty", "is_published", "created_at") VALUES (7, 5, 'Academic librarian', 'SKU-TSN-9201', 68.74, 1065, True, '2025-09-28T05:40:06.717515');
INSERT INTO "products" ("id", "category_id", "title", "sku", "price", "stock_qty", "is_published", "created_at") VALUES (8, 9, 'TEFL teacher', 'SKU-MPU-4258', 42.27, 5304, True, '2025-10-23T21:01:32.125486');
INSERT INTO "products" ("id", "category_id", "title", "sku", "price", "stock_qty", "is_published", "created_at") VALUES (9, 6, 'Private music teacher', 'SKU-RNG-9005', 25.02, 8780, False, '2025-10-29T20:44:56.095175');
INSERT INTO "products" ("id", "category_id", "title", "sku", "price", "stock_qty", "is_published", "created_at") VALUES (10, 2, 'Doctor, general practice', 'SKU-QFS-8962', 34.86, 6597, False, '2025-11-29T17:43:58.995128');

-- Table: order_items (10 records)
INSERT INTO "order_items" ("id", "order_id", "product_id", "quantity", "unit_price") VALUES (1, 3, 5, 26, 82.09);
INSERT INTO "order_items" ("id", "order_id", "product_id", "quantity", "unit_price") VALUES (2, 7, 6, 22, 34.04);
INSERT INTO "order_items" ("id", "order_id", "product_id", "quantity", "unit_price") VALUES (3, 4, 2, 17, 38.76);
INSERT INTO "order_items" ("id", "order_id", "product_id", "quantity", "unit_price") VALUES (4, 4, 1, 4, 41.82);
INSERT INTO "order_items" ("id", "order_id", "product_id", "quantity", "unit_price") VALUES (5, 1, 6, 4, 11.18);
INSERT INTO "order_items" ("id", "order_id", "product_id", "quantity", "unit_price") VALUES (6, 4, 9, 7, 133.41);
INSERT INTO "order_items" ("id", "order_id", "product_id", "quantity", "unit_price") VALUES (7, 8, 4, 39, 55.77);
INSERT INTO "order_items" ("id", "order_id", "product_id", "quantity", "unit_price") VALUES (8, 2, 7, 18, 13.52);
INSERT INTO "order_items" ("id", "order_id", "product_id", "quantity", "unit_price") VALUES (9, 1, 2, 3, 159.28);
INSERT INTO "order_items" ("id", "order_id", "product_id", "quantity", "unit_price") VALUES (10, 2, 4, 10, 35.09);

-- Table: reviews (10 records)
INSERT INTO "reviews" ("id", "user_id", "product_id", "rating", "comment", "created_at") VALUES (1, 3, 5, 3, 'Behavior weight dog financial southern challenge. Each little sure. Lay though offer responsibility. Manager during prevent accept seem show.', '2025-02-04T01:42:47.357219');
INSERT INTO "reviews" ("id", "user_id", "product_id", "rating", "comment", "created_at") VALUES (2, 2, 8, 4, 'Compare when military anyone eat. Lead soon property write. Fish sense kind spring throughout interview trade knowledge.', '2025-03-14T11:21:21.141294');
INSERT INTO "reviews" ("id", "user_id", "product_id", "rating", "comment", "created_at") VALUES (3, 9, 2, 1, 'Else easy point she miss phone ever. Require doctor from throw. Catch discuss really relationship.', '2025-01-04T03:06:18.771122');
INSERT INTO "reviews" ("id", "user_id", "product_id", "rating", "comment", "created_at") VALUES (4, 9, 1, 5, 'My indeed deal information toward once. Task she herself. Wall fear hope.', '2026-08-31T12:54:26.493067');
INSERT INTO "reviews" ("id", "user_id", "product_id", "rating", "comment", "created_at") VALUES (5, 4, 3, 3, 'Section national owner determine detail job ahead. Protect something right subject try wonder. Agree hour north agree poor career left.', '2024-12-24T22:38:30.807715');
INSERT INTO "reviews" ("id", "user_id", "product_id", "rating", "comment", "created_at") VALUES (6, 8, 4, 4, 'Deep force seven here sell story. Strong like see appear weight. Practice sit prepare senior wear.', '2025-04-12T20:10:17.844189');
INSERT INTO "reviews" ("id", "user_id", "product_id", "rating", "comment", "created_at") VALUES (7, 1, 3, 3, 'Charge call prove nor design record short cold.', '2026-02-04T19:02:50.702755');
INSERT INTO "reviews" ("id", "user_id", "product_id", "rating", "comment", "created_at") VALUES (8, 7, 5, 5, 'Who blue agent find. However resource away real physical big.', '2026-06-05T11:50:23.702904');
INSERT INTO "reviews" ("id", "user_id", "product_id", "rating", "comment", "created_at") VALUES (9, 8, 5, 3, 'Someone not American mouth. Attention positive actually information majority item. Player stock religious itself safe whole. Pattern try simple let stay.', '2026-01-25T00:03:23.280988');
INSERT INTO "reviews" ("id", "user_id", "product_id", "rating", "comment", "created_at") VALUES (10, 9, 8, 2, 'Store beautiful think during let. Property from management foot maintain great election evidence. Red everybody act way beat result major serve.', '2026-04-06T16:30:26.208097');

COMMIT;