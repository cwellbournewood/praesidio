// Praesidio JetBrains plugin — root project settings.
//
// Single-module Gradle build. The plugin is published as a single .zip
// suitable for the JetBrains Marketplace and for sideload via
// Settings → Plugins → ⚙ → Install Plugin from Disk…

pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        mavenCentral()
        // IntelliJ Platform artifacts.
        maven("https://www.jetbrains.com/intellij-repository/releases")
        maven("https://cache-redirector.jetbrains.com/intellij-dependencies")
    }
}

rootProject.name = "praesidio-jetbrains"
