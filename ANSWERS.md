# Lab 5: Asynchronous Event-Driven Weekly Meetings Report — Відповіді на запитання

---

## Частина 1. Обов'язкові відповіді для здачі (Part 3, Step 7)

### Запитання 0: Send the same week twice. How many emails do you get? Write down why.
*(Надішліть один і той самий тиждень двічі. Скільки листів ви отримаєте? Опишіть, чому.)*

**Відповідь:**  
Отримувач отримує **два ідентичні листи**.

**Чому це відбувається:**
1. **Генерація звіту (Builder):** Операція запису файлу в S3 (`s3.put_object(reports/2026-W40.csv)`) є **ідемпотентною** щодо даних — новий файл просто перезаписує старий з тим самим ключем.
2. **Подія S3 (Event):** Щоразу, коли файл завантажується або перезаписується в S3, бакет генерує нову подію `s3:ObjectCreated:Put`.
3. **Поштовик (Mailer):** Отримує кожну таку подію окремо. Оскільки поштовик не зберігає внутрішнього стану про те, чи надсилався вже цей звіт раніше, надсилання листа через SES є **неідемпотентною операцією**. Відповідно, 2 завантаження = 2 події = 2 надіслані листи.

---

### Запитання 1: The mailer got the same ObjectCreated event twice, and the person got two identical emails. Where would you store "this report was already sent", and what would the key be?
*(Поштовик отримав одну й ту саму подію ObjectCreated двічі, і людина отримала два однакових листи. Де б ви зберігали запис «цей звіт уже надіслано» і яким був би ключ?)*

**Відповідь:**
- **Де зберігати:** Найкраще рішення в AWS — таблиця **Amazon DynamoDB** з увімкненим TTL (Time-To-Live, наприклад, 30–60 днів) або рядок у таблиці бази даних із підтримкою атомарних операцій.
- **Первинний ключ (Key):**  
  - Якщо один звіт відправляється списку отримувачів загалом: `report_key = "reports/2026-W40.csv"` (або комбінація року й тижня `week = "2026-W40"`).  
  - Якщо в системі є персоналізовані звіти: складений ключ `(recipient_email, report_key)`.
- **Як реалізувати захист від дублікатів (Idempotency Check):**  
  Перед викликом `ses.send_email` поштовик робить умовний запис у DynamoDB:
  ```python
  dynamodb.put_item(
      TableName="sent_reports",
      Item={
          "report_key": {"S": key},
          "sent_at": {"S": datetime.now(timezone.utc).isoformat()},
      },
      ConditionExpression="attribute_not_exists(report_key)",
  )
  ```
  - Якщо запис успішний — відправляємо email.
  - Якщо повертається помилка `ConditionalCheckFailedException` — звіт уже відправлявся; функція безпечно виходить без повторної відправки.

---

### Запитання 2: The builder in the VPC could not reach SES. List three ways to fix that, with their monthly cost: a NAT gateway, a VPC interface endpoint for SES, and the split you built. Which would you choose with ten more emails a week? With a million?
*(Генератор у VPC не міг достукатися до SES. Назвіть три способи це вирішити з їхньою помісячною вартістю: NAT Gateway, VPC Interface Endpoint для SES та архітектурний розподіл (split), який ви побудували. Який би ви обрали для 10 додаткових листів на тиждень? А для 1 мільйона?)*

**Відповідь:**

#### Три способи та їхня вартість:

1. **NAT Gateway (у публічній підмережі VPC):**
   - **Як працює:** Дозволяє лямбді у приватній підмережі виходити в публічний інтернет до будь-яких AWS API.
   - **Вартість:** ~$32.40/місяць за один шлюз ($0.045/годину) + $0.045 за кожен GB обробленого трафіку. При розгортанні у двох зонах доступності (Multi-AZ) — ~$65/місяць.

2. **VPC Interface Endpoint (AWS PrivateLink) для SES:**
   - **Як працює:** Створює мережевий інтерфейс (ENI) з приватною IP-адресою у вашій підмережі для прямого звернення до API SES без виходу в інтернет.
   - **Вартість:** ~$7.20/місяць за одну AZ ($0.01/годину) + $0.01 за кожен GB трафіку. Для 2 AZ — ~$14.40/місяць.

3. **Архітектурний розподіл (Split Architecture — наш варіант):**
   - **Як працює:** 
     - `report-builder` працює у VPC і кладе файл в S3 через **S3 Gateway VPC Endpoint** (який надається AWS **безкоштовно**);
     - завантаження файлу генерує подію `ObjectCreated`;
     - `report-mailer` працює **поза VPC**, отримує подію, читає файл з S3 і напряму безкоштовно відправляє через публічний ендпоінт SES.
   - **Вартість:** **$0.00/місяць** фіксованих витрат на мережеву інфраструктуру (Gateway Endpoints безкоштовні).

#### Який варіант обрати:
- **Для +10 листів на тиждень:**  
  Однозначно **Split Architecture (розподіл)**. Платити $32/міс за NAT Gateway або $7–14/міс за Interface Endpoint заради 10 листів на тиждень економічно не має сенсу.
- **Для 1 000 000 листів на тиждень:**  
  Також **Split Architecture** або **VPC Interface Endpoint**:
  - Розподілена архітектура залишається найкращою інженерною практикою: вона усуває навантаження мережі VPC під час масової розсилки, ізолює відправку пошти від пулу з'єднань бази даних і коштує $0 фіксованих витрат.
  - Якщо ж з міркувань суворої безпеки (наприклад, банківський комплаєнс) заборонено тримати функції поза VPC, обирається **VPC Interface Endpoint** (~$7.20/міс), оскільки він у 4 рази дешевший за NAT Gateway і не відкриває вихід у публічний інтернет.

---

### Запитання 3: You could send a presigned S3 link instead of an attachment. A presigned URL signed with a Lambda role's temporary credentials stops working when those credentials expire, often within hours. How would you send a link that works for a week?
*(Ви могли б надіслати підписане посилання (Presigned S3 link) замість вкладення. Посилання, підписане тимчасовими ключами ролі Lambda, перестає працювати разом із закінченням терміну дії цих ключів (часто протягом кількох годин). Як надіслати посилання, яке працюватиме тиждень?)*

**Відповідь:**
Тимчасові облікові дані IAM ролі Lambda (отримані через AWS STS) діють максимум від 1 до 6 годин (максимум до 12 годин), тому S3 Presigned URL, згенерований такою роллю, не може бути дійсним довше за життя сесії STS.

**Способи реалізації посилання на 7 днів:**
1. **CloudFront Signed URLs (рекомендований стандарт AWS):**  
   Зберігати S3 бакет повністю закритим, налаштувати дистрибуцію CloudFront з Origin Access Control (OAC) та генерувати **підписані посилання CloudFront (Signed URLs)** за допомогою окремого закритого ключа (Key Group / Public-Private Key Pair). Такі посилання можуть мати будь-який термін життя (зокрема 7 днів) незалежно від STS-токенів Lambda.
2. **Використання довготривалих IAM-ключів:**  
   Використати для генерації Presigned URL виділеного IAM-користувача (з мінімальними правами `s3:GetObject` на префікс `reports/*`), ключі якого не закінчуються щогодини (хоча підхід із CloudFront вважається безпечнішим).
3. **Генерація посилання на льоту через API:**  
   Замість прямого посилання на файл надсилати в листі посилання на веб-додаток: `https://app.example.com/reports/download?token=...`. Коли користувач клікає, бекенд автентифікує користувача, генерує свіже короткоживуче Presigned URL на 15 хвилин і віддає HTTP 302 Redirect.

---

## Частина 2. Питання для обговорення на занятті (Class Discussion)

### The pattern (Архітектурний патерн)

1. **In the cake shop, what is the command and what is the event? Find both in your lab.**  
   - *Команда (Command):* Запит на виконання певної дії з конкретними параметрами («Спекти торт Наполеон»). У лабораторній це повідомлення в SQS: `{"week": "2026-W41", "source": "sqs"}`.
   - *Подія (Event):* Факт у минулому часі про те, що щось уже відбулося («Торт готовий і стоїть на полиці»). У лабораторній це подія S3: `s3:ObjectCreated:Put` для файлу `reports/2026-W41.csv`.

2. **McDonald's returns a receipt number at once. A web API does the same with 202 and a job id. What does the user see while the job is running, and what should they see if it fails?**  
   - Поки завдання виконується: Користувач бачить статус «Обробляється» (Pending / In Progress), індикатор завантаження або прогрес-бар. Фронтенд періодично опитує бекенд (`GET /jobs/<job_id>`) або отримує WebSocket/SSE-повідомлення.
   - Якщо завдання впало: Користувач бачить статус «Помилка генерації звіту», зрозуміле пояснення проблеми (без сирих стек-трейсів) та кнопку «Спробувати знову» (Retry).

3. **"At least once" means your task can run twice. Which of your steps are idempotent, and which are not?**  
   - **Ідемпотентні:**
     - Запит до бази даних (`SELECT ...`) — читання не змінює стан.
     - Запис файлу в S3 (`s3.put_object(reports/2026-W40.csv)`) — повторний запис того самого файлу дає той самий результат у сховищі.
   - **Неідемпотентні:**
     - Відправка листа через SES (`ses.send_email`) — кожен виклик відправляє окремий лист.

4. **The report reads the database at 07:00 on Monday. A meeting from last week is edited at 07:01. Is the report wrong? What does eventual consistency mean for a weekly report?**  
   - Ні, звіт не є помилковим: він фіксує стан системи (знімок даних) строго на момент його генерації (07:00).
   - *Eventual consistency:* означає, що зміни стають видимими не миттєво для всіх спостерігачів, а з часом. Якщо вимога вимагає «перерахунок протягом 5 хвилин після зміни календаря», то редагування зустрічі має саме по собі породжувати подію `MeetingUpdated`, яка ставить у чергу позачергову регенерацію звіту за цей тиждень.

5. **You want to add a Slack notification when a report is ready. What do you change in the builder?**  
   - **Відповідь: «Нічого» (Nothing).**  
   - *Чому:* Архітектура побудована на подіях (Event-Driven). Генератор (Builder) лише створює факт — завантажує файл у S3. Будь-який новий сервіс (відправка в Slack, аналітика тощо) просто підписується на ту саму подію `s3:ObjectCreated` (через EventBridge або SNS/SQS топік), і генератор навіть не знає про їх існування (Loose Coupling).

---

### The self-hosted alternatives (Альтернативи без AWS)

1. **A payment service sends an event for every successful payment, and losing one means a customer paid for nothing. Redis or RabbitMQ?**  
   - **RabbitMQ.**  
   - *Обґрунтування:* RabbitMQ спроєктований як надійний брокер повідомлень (AMQP). Повідомлення зберігаються на диску (durable queues, persistent messages), вимагають явного підтвердження обробки від споживача (`ack`), а при падінні воркера повертаються в чергу. Redis за замовчуванням зберігає дані в пам'яті, а при операції вилучення зі списку (`LPOP/BLPOP`) повідомлення зникає з черги ще до того, як воркер завершить його обробку; падіння процесу або рестарт Redis може призвести до втрати платежу.

2. **RQ stores the job as a pickled Python call. What happens to the jobs in the queue when you rename the task function and deploy? What does that tell you about message formats between services?**  
   - Якщо перейменувати функцію в коді, воркери впадуть з помилкою `AttributeError` або `ModuleNotFoundError` при спробі розпакувати pickle (`unpickle`), оскільки в черзі лежить пряме посилання на стару назву функції.
   - *Висновок:* Повідомлення між сервісами мають бути нейтральними до платформи та мови (структурований JSON або Protocol Buffers із версіонуванням полів), а не серіалізованим внутрішнім кодом конкретної мови.

3. **Celery beat runs schedules in a separate process. What happens if you run two copies of it? What is the AWS equivalent of beat, and why does it not have this problem?**  
   - Якщо запустити дві копії Celery Beat, кожна з них спрацює одночасно і надішле дублікат завдання в чергу (звіт створиться і надішлеться двічі).
   - AWS-еквівалент: **Amazon EventBridge Scheduler**. Це повністю керований розподілений сервіс AWS, де розклад існує як єдина сутність і гарантує одноразовий запуск розкладу без потреби керувати окремими процесами-демонами.

---

### AWS (Особливості сервісів)

1. **Why does the schedule send a message to SQS instead of invoking the function directly? Name a case where invoking directly is the better choice.**  
   - *Чому SQS:*
     1. **Надійність та DLQ:** Якщо база даних спить або впала, повідомлення залишається в черзі і повторюється 3 рази, після чого потрапляє в DLQ замість того, щоб безслідно зникнути.
     2. **Згладжування навантаження (Buffering):** Не перевантажує ліміти паралелізму Lambda та Aurora.
     3. **Єдина точка входу:** І розклад, і ручний запуск (`make report-now`) використовують одну чергу.
   - *Коли краще викликати напряму:* Коли операція є строго синхронною (користувач чекає на відповідь у браузері прямо зараз), або для легких атомарних завдань, де немає складних залежностей і затримка черги є зайвою.

2. **Why must the SQS visibility timeout be longer than the function timeout? Describe exactly what goes wrong if it is shorter.**  
   - *Чому:* Visibility Timeout має бути в 6 разів більшим за таймаут Lambda (як рекомендує AWS).
   - *Що піде не так, якщо він коротший:* Якщо лямбда виконує важкий звіт протягом 60 секунд, а Visibility Timeout черги становить 30 секунд, то через 30 секунд SQS вирішить, що перша лямбда померла, і віддасть це саме повідомлення **другому екземпляру лямбди**. Обидва екземпляри будуть паралельно обробляти одне й те саме завдання, створюючи подвійне навантаження на базу та дублікати звітів.

3. **A message lands in the DLQ on Sunday night. Who finds out, and how? Design the alarm.**  
   - **Дизайн алярму:**
     1. Створюється CloudWatch Alarm на метрику SQS `ApproximateNumberOfMessagesVisible` для черги DLQ (`meetings-report-requests-dlq`).
     2. Умова: `Metric > 0` за період 1 хвилина.
     3. Дія (Action): Відправка сповіщення в **Amazon SNS Topic**.
     4. Підписники SNS: Email чергового інженера або інтеграція SNS з PagerDuty / Slack Webhook.

4. **The builder wakes Aurora up every Monday. What does that cost per month? What would it cost if the builder ran every five minutes instead?**  
   - *Раз на тиждень (щопонеділка):* Aurora Serverless v2 масштабується від 0.5 ACU ($0.12 за ACU-годину). Генерація звіту займає менше 1 секунди, після чого Aurora повертається до сну через 15–20 хвилин простою. Це коштує лічені центи на місяць (~$0.02–$0.05/міс).
   - *Кожні 5 хвилин:* Якщо запускати кожні 5 хвилин, Aurora взагалі ніколи не встигне заснути (таймаут засинання становить 15 хв). База працюватиме безперервно 24/7 на мінімумі 0.5 ACU: `730 годин * 0.5 ACU * $0.12 = ~$43.80/місяць`.

5. **EventBridge Scheduler, SQS and S3 notifications are each nearly free at this volume. SES is $0.10 per thousand emails. At what point does this design start to cost money, and which part first?**  
   - За поточного навантаження все вкладається в безкоштовні рівні AWS Free Tier.
   - Першим починає коштувати гроші:
     - **Aurora Serverless v2:** Якщо період запуску зменшити (наприклад, кожні кілька хвилин), саме Aurora згенерує найбільший рахунок (~$43/міс за постійну роботу).
     - При зростанні кількості звітів до сотень тисяч: **Amazon SES** ($0.10 за 1 000 листів) та зберігання великої кількості звітів в **S3** (якщо не налаштовано наш Lifecycle Rule на видалення через 90 днів).
