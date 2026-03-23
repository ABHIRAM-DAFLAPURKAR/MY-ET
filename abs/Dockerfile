# Build Stage
FROM maven:3.9.6-eclipse-temurin-17 AS build
WORKDIR /app

# Cache dependencies
COPY pom.xml .
RUN mvn dependency:go-offline -B

# Build source
COPY src ./src
RUN mvn clean package -DskipTests -B

# Final Runtime Stage (Using JRE for smaller footprint)
FROM eclipse-temurin:17-jre-alpine
WORKDIR /app

# Non-root user for security (Recommended for production-ready apps)
RUN addgroup -S spring && adduser -S spring -G spring
USER spring:spring

COPY --from=build /app/target/*.jar app.jar

EXPOSE 8080
ENTRYPOINT ["java", "-Dspring.profiles.active=docker", "-jar", "app.jar"]