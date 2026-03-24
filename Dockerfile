FROM odoo:18.0

USER root

# Install extra dependencies if needed
RUN pip3 install num2words xlwt

# Create directories
RUN mkdir -p /etc/odoo /mnt/extra-addons /var/lib/odoo

# Copy config file
COPY ./config/odoo.conf /etc/odoo/odoo.conf

# Copy your custom addons from GitHub repo
COPY ./addons /mnt/extra-addons

# Fix permissions
RUN chown -R odoo:odoo /etc/odoo /mnt/extra-addons /var/lib/odoo

USER odoo