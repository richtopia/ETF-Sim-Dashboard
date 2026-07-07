FROM nginx:alpine

# Copy the dashboard payload (including results.json) into the default Nginx web root
COPY dashboard/ /usr/share/nginx/html/

# Expose standard HTTP port
EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
