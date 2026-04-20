{{/*
Expand the name of the chart.
*/}}
{{- define "heliox.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this.
*/}}
{{- define "heliox.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart label value: "heliox-0.1.0"
*/}}
{{- define "heliox.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels applied to every resource.
*/}}
{{- define "heliox.labels" -}}
helm.sh/chart: {{ include "heliox.chart" . }}
{{ include "heliox.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels used in matchLabels and pod template labels.
*/}}
{{- define "heliox.selectorLabels" -}}
app.kubernetes.io/name: {{ include "heliox.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Return the ServiceAccount name.
*/}}
{{- define "heliox.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "heliox.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Return the name of the Secret that holds application secrets.
When secrets.existingSecret is set, use that; otherwise use the generated name.
*/}}
{{- define "heliox.secretName" -}}
{{- if .Values.secrets.existingSecret }}
{{- .Values.secrets.existingSecret }}
{{- else }}
{{- printf "%s-secrets" (include "heliox.fullname" .) }}
{{- end }}
{{- end }}

{{/*
Return the name of the ConfigMap.
*/}}
{{- define "heliox.configMapName" -}}
{{- printf "%s-config" (include "heliox.fullname" .) }}
{{- end }}

{{/*
Build the DATABASE_URL from postgresql.external values and the db password secret.
Used in the API, worker, beat, and migrations containers.
*/}}
{{- define "heliox.databaseUrl" -}}
{{- if .Values.postgresql.enabled }}
{{- printf "postgresql+psycopg2://%s:$(DATABASE_PASSWORD)@%s-postgresql:5432/%s" .Values.postgresql.external.username (include "heliox.fullname" .) .Values.postgresql.external.database }}
{{- else }}
{{- printf "postgresql+psycopg2://%s:$(DATABASE_PASSWORD)@%s:%d/%s" .Values.postgresql.external.username .Values.postgresql.external.host (int .Values.postgresql.external.port) .Values.postgresql.external.database }}
{{- end }}
{{- end }}

{{/*
Return the Redis URL. Uses the bundled Redis subchart when redis.enabled=true,
otherwise falls back to config.redisUrl.
*/}}
{{- define "heliox.redisUrl" -}}
{{- if .Values.redis.enabled }}
{{- if .Values.redis.auth.enabled }}
{{- printf "redis://:$(REDIS_PASSWORD)@%s-redis-master:6379/0" (include "heliox.fullname" .) }}
{{- else }}
{{- printf "redis://%s-redis-master:6379/0" (include "heliox.fullname" .) }}
{{- end }}
{{- else }}
{{- .Values.config.redisUrl }}
{{- end }}
{{- end }}

{{/*
Return the image registry prefix, falling back to global.imageRegistry.
Usage: {{ include "heliox.imageRepository" (dict "repo" .Values.api.image.repository "global" .Values.global) }}
*/}}
{{- define "heliox.imageRepository" -}}
{{- if .global.imageRegistry }}
{{- printf "%s/%s" .global.imageRegistry .repo }}
{{- else }}
{{- .repo }}
{{- end }}
{{- end }}

{{/*
Standard envFrom block referencing the ConfigMap and Secret.
Used in api, worker, beat, and migrations.
*/}}
{{- define "heliox.envFrom" -}}
- configMapRef:
    name: {{ include "heliox.configMapName" . }}
- secretRef:
    name: {{ include "heliox.secretName" . }}
{{- end }}
