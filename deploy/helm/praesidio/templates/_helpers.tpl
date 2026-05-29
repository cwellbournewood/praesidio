{{/*
Expand the name of the chart.
*/}}
{{- define "praesidio.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "praesidio.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{/*
Chart name + version label.
*/}}
{{- define "praesidio.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Common labels applied to every object.
*/}}
{{- define "praesidio.labels" -}}
helm.sh/chart: {{ include "praesidio.chart" . }}
{{ include "praesidio.selectorLabels" . }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: praesidio
{{- with .Values.commonLabels }}
{{ toYaml . }}
{{- end }}
{{- end -}}

{{/*
Selector labels (stable, never include version-bound values).
*/}}
{{- define "praesidio.selectorLabels" -}}
app.kubernetes.io/name: {{ include "praesidio.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{/*
Per-component labels (gateway / ui / postgres / redis).
Usage: include "praesidio.componentLabels" (dict "ctx" . "component" "gateway")
*/}}
{{- define "praesidio.componentLabels" -}}
{{- $ctx := .ctx -}}
{{ include "praesidio.labels" $ctx }}
app.kubernetes.io/component: {{ .component }}
{{- end -}}

{{- define "praesidio.componentSelectorLabels" -}}
{{- $ctx := .ctx -}}
{{ include "praesidio.selectorLabels" $ctx }}
app.kubernetes.io/component: {{ .component }}
{{- end -}}

{{/*
Component fullname (release-name-component).
*/}}
{{- define "praesidio.componentName" -}}
{{- printf "%s-%s" (include "praesidio.fullname" .ctx) .component | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Common annotations.
*/}}
{{- define "praesidio.annotations" -}}
{{- with .Values.commonAnnotations }}
{{ toYaml . }}
{{- end }}
{{- end -}}

{{/*
ServiceAccount name.
*/}}
{{- define "praesidio.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "praesidio.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}

{{/*
Image reference. Usage: include "praesidio.image" (dict "img" .Values.image.gateway "ctx" .)
*/}}
{{- define "praesidio.image" -}}
{{- $img := .img -}}
{{- $tag := default .ctx.Chart.AppVersion $img.tag -}}
{{- printf "%s:%s" $img.repository $tag -}}
{{- end -}}

{{/*
Postgres host: embedded or external (DSN parsed by gateway).
Returned only when embedded is true; otherwise the DSN secret/env wins.
*/}}
{{- define "praesidio.postgresHost" -}}
{{- if .Values.postgres.embedded -}}
{{- printf "%s-postgres" (include "praesidio.fullname" .) -}}
{{- end -}}
{{- end -}}

{{/*
Redis host (embedded).
*/}}
{{- define "praesidio.redisHost" -}}
{{- if .Values.redis.embedded -}}
{{- printf "%s-redis" (include "praesidio.fullname" .) -}}
{{- end -}}
{{- end -}}

{{/*
DATABASE_URL value: embedded vs external.
*/}}
{{- define "praesidio.databaseUrl" -}}
{{- if .Values.postgres.embedded -}}
{{- printf "postgresql+asyncpg://praesidio:praesidio@%s-postgres:5432/praesidio" (include "praesidio.fullname" .) -}}
{{- else -}}
{{- .Values.postgres.externalDSN -}}
{{- end -}}
{{- end -}}

{{/*
REDIS_URL value: embedded vs external.
*/}}
{{- define "praesidio.redisUrl" -}}
{{- if .Values.redis.embedded -}}
{{- printf "redis://%s-redis:6379/0" (include "praesidio.fullname" .) -}}
{{- else -}}
{{- .Values.redis.externalURL -}}
{{- end -}}
{{- end -}}

{{/*
Secret name for the gateway. Centralised so deployment + externalsecret agree.
*/}}
{{- define "praesidio.gatewaySecretName" -}}
{{- printf "%s-gateway" (include "praesidio.fullname" .) -}}
{{- end -}}

{{/*
ConfigMap name for the policy bundle.
*/}}
{{- define "praesidio.policyConfigMapName" -}}
{{- printf "%s-policies" (include "praesidio.fullname" .) -}}
{{- end -}}
