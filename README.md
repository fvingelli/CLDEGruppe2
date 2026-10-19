# Cloudwalker – Fitness-Tracker in der AWS-Cloud

Du erfasst Trainings, die Cloud berechnet Tempo, Geschwindigkeit, Kalorien und Statistiken, und jedes Training ist **privat** oder **öffentlich** (Community-Feed).

```
Browser (S3 Static Website)
   │  Login (E-Mail + Passwort)         ┌──────────────┐
   ├───────────────────────────────────►│   Cognito    │
   │  JWT                               └──────────────┘
   │  /workouts /stats (JWT)  ┌─────────────┐  ┌────────┐  ┌──────────────────────┐
   └─────────────────────────►│ API Gateway ├─►│ Lambda ├─►│ DynamoDB             │
      /feed (ohne Login)      └─────────────┘  └────────┘  │  Tabelle: Trainings  │
                                                           │  Index: nur public   │
                                                           └──────────────────────┘
```

## Was wo passiert

| Schritt | Wo |
|---|---|
| Erfassen | Formular im Browser → `POST /workouts` |
| Verarbeiten | Lambda: Validierung, Tempo (min/km), km/h, Kalorien (MET × Gewicht × Stunden), Wochenwerte, Serie, Bestleistungen |
| Privat / öffentlich | Feld `visibility`. Nur öffentliche Einträge bekommen das Attribut `feedPk` und landen im Index `feed-index` (Sparse Index). Private Trainings sind per Design nie im Feed. |
| Datenschutz | Der Feed zeigt nur den Teil der E-Mail vor dem `@`, nie E-Mail oder User-ID. Jede Route ausser `/feed` verlangt ein gültiges Cognito-Token; Lambda liest und schreibt nur Einträge der eigenen User-ID. |

## Lokal ausprobieren (ohne AWS)

`frontend/index.html` im Browser öffnen. Solange `config.js` leer ist, läuft der Demo-Modus mit lokalem Speicher und ein paar Beispiel-Posts im Feed.

## Deploy im AWS Learner Lab

Voraussetzung: AWS CLI mit den Credentials aus dem Learner Lab («AWS Details»).

```bash
# 1) Lambda packen und hochladen
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
CODE_BUCKET=cloudwalker-code-$ACCOUNT
aws s3 mb s3://$CODE_BUCKET
(cd backend && zip ../cloudwalker-lambda.zip lambda_function.py)
aws s3 cp cloudwalker-lambda.zip s3://$CODE_BUCKET/

# 2) Stack erstellen (nutzt die vorhandene LabRole, es werden keine IAM-Rollen angelegt)
ROLE=$(aws iam get-role --role-name LabRole --query Role.Arn --output text)
aws cloudformation deploy --stack-name cloudwalker --template-file template.yaml \
  --parameter-overrides LabRoleArn=$ROLE CodeBucket=$CODE_BUCKET

# 3) Outputs lesen
aws cloudformation describe-stacks --stack-name cloudwalker \
  --query "Stacks[0].Outputs" --output table
```

4. `frontend/config.js` ausfüllen: `region`, `userPoolClientId`, `apiUrl` aus den Outputs (apiUrl ohne `/` am Ende).
5. Frontend hochladen und öffnen:

```bash
aws s3 sync frontend s3://<SiteBucketName>
# Adresse: Output «SiteUrl»
```

Beim Registrieren schickt Cognito einen Bestätigungscode per E-Mail. Die App fragt ihn direkt ab.

## Hinweise

- Die Website läuft über HTTP (S3-Website-Endpoint). Für HTTPS bräuchte es CloudFront, das im Learner Lab oft gesperrt ist.
- Blockiert deine Lab-Umgebung öffentliche Bucket-Policies, schlägt der Stack bei `SiteBucket` fehl. Lass dann die zwei S3-Ressourcen aus dem Template weg und teste das Frontend lokal gegen die API.
- Lambda-Code ändern: ZIP neu bauen, hochladen, dann `aws lambda update-function-code --function-name cloudwalker-api --s3-bucket $CODE_BUCKET --s3-key cloudwalker-lambda.zip`.
- Aufräumen: Buckets leeren (`aws s3 rm s3://<bucket> --recursive`), dann `aws cloudformation delete-stack --stack-name cloudwalker`.
- Naheliegende Erweiterungen: Likes/Kommentare im Feed, Monatsauswertung, Ziele, CloudWatch-Dashboard.
