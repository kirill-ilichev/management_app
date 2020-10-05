import os
import time

from boto.ec2.cloudwatch import MetricAlarm

from compat import get_connection
from local import INSTANCE_TEMPLATE_ID, SECURITY_GROUP_IDS, NGINX_CONFIG_PATH
from nginxparser import load, dump


def get_aws_access():
    return {
        "aws_access_key_id": os.environ.get("AWS_ACCESS_KEY_ID"),
        "aws_secret_access_key": os.environ.get("AWS_SECRET_ACCESS_KEY")
    }


def get_upstream_ips():
    """
    Nginx parser for upstream ips for nginx conf file structure as in
    nginx/load_balancer.conf file
    """
    nginx_conf = load(open(NGINX_CONFIG_PATH))
    upstream_conf = [elem for elem in nginx_conf if elem[0][0] == 'upstream'][0]
    upstream_ips = [elem[1] for elem in upstream_conf[1][1:]]
    return upstream_ips


def get_upstream_instances(connection, upstream_ips):
    instances = connection.get_only_instances()
    upstream_instances = [instance for instance in instances
                          if instance.ip_address in upstream_ips]

    return upstream_instances


def create_additional_node(ec2_connection, cw_connection):
    # create new instance
    new_node = ec2_connection.run_instances(
        INSTANCE_TEMPLATE_ID,
        security_group_ids=SECURITY_GROUP_IDS,
        instance_type="m1.medium",
        user_data=(
            "#!/bin/bash\n"
            "sudo /usr/local/bin/docker-compose -f"
            "/home/ec2-user/croc_cloud_tz/docker-compose.yml up")

    )
    new_node_instance_id = new_node.instances[0].id
    while True:
        new_instance = ec2_connection.get_all_instances(
            [new_node_instance_id]
        )[0].instances[0]
        # waiting for instance
        if new_instance.state != 'running':
            time.sleep(1)
            continue
        # get elastic ip of created instance
        elastic_ip = new_instance.ip_address
        if not elastic_ip:
            # create elastic ip if new instance dont have ip
            elastic_ip = ec2_connection.allocate_address().public_ip
            ec2_connection.associate_address(
                new_node_instance_id,
                elastic_ip,
                allow_reassociation=True
            )
        break

    # Create alarm for CPU. Alarm if CPU > 70%. Check it every 2 minutes
    alarm = MetricAlarm(
        cw_connection,
        '{0} CPU Alarm'.format(new_node_instance_id),
        'CPUUtilization',
        'AWS/EC2',
        'Maximum',
        '>',
        70.0,
        60,
        1,
        dimensions={'InstanceId': [new_node_instance_id]},
    )
    cw_connection.put_metric_alarm(alarm)
    return elastic_ip


def get_upstream_line_idx(nginx_conf):
    """Get index of line in nginx conf with upstream"""
    idx = None
    for idx, line in enumerate(nginx_conf):
        if "upstream" in line[0]:
            break
    return idx


def add_ips_to_nginx_upstream_conf(ips):
    """Add new ips to nginx upstream config"""
    nginx_conf = load(open(NGINX_CONFIG_PATH))
    upstream_line_idx = get_upstream_line_idx(nginx_conf)
    for ip in ips:
        nginx_conf[upstream_line_idx][1].append(["server", ip])

    dump(nginx_conf, open(NGINX_CONFIG_PATH, "w"))


def remove_ips_from_nginx_upstream_conf(ips):
    """Remove ips from nginx upstream config"""
    nginx_conf = load(open(NGINX_CONFIG_PATH))
    upstream_line_idx = get_upstream_line_idx(nginx_conf)
    for ip in ips:
        nginx_conf[upstream_line_idx][1].remove(["server", ip])
    dump(nginx_conf, open(NGINX_CONFIG_PATH, "w"))


def management():
    """Management app, that provides balance of nodes in chain of instances"""
    aws_access = get_aws_access()

    ec2_endpoint = os.environ.get("EC2_URL")
    ec2_connection = get_connection("ec2", ec2_endpoint, **aws_access)

    upstream_ips = get_upstream_ips()
    nodes = get_upstream_instances(ec2_connection, upstream_ips)

    cw_endpoint = os.environ.get("AWS_CLOUDWATCH_URL")
    cw_connection = get_connection("cw", cw_endpoint, **aws_access)

    # get cpu alarms of nodes from nginx conf
    cpu_alarms = []
    for node in nodes:
        cpu_alarms.append(
            cw_connection
            .describe_alarms_for_metric(
                'CPUUtilization',
                'AWS/EC2',
                dimensions={"InstanceId": [node.id]}
            )[0]
        )

    count_of_alarms_with_alarm_status = len(
        [alarm for alarm in cpu_alarms if alarm.state_value == 'alarm']
    )

    # create additional nodes
    new_elastic_ips = []
    for _ in range(count_of_alarms_with_alarm_status):
        elastic_ip = create_additional_node(ec2_connection, cw_connection)
        new_elastic_ips.append(elastic_ip)

    additional_nodes = [node for node in nodes
                        if node.image_id == INSTANCE_TEMPLATE_ID]

    additional_nodes_ids = [node.id for node in additional_nodes]

    # if all nodes with normal CPU we dont need additional nodes
    terminated_instances = []
    if (additional_nodes_ids and cpu_alarms and
            all(alarm.state_value == 'ok' for alarm in cpu_alarms)):
        terminated_instances = additional_nodes
        ec2_connection.terminate_instances(additional_nodes_ids)
        cw_connection.delete_alarms([
            '{0} CPU Alarm'.format(node_id) for node_id in additional_nodes_ids
        ])

    # add elastic ips to nginx
    if new_elastic_ips:
        add_ips_to_nginx_upstream_conf(new_elastic_ips)

    # remove terminated ips from nginx conf
    if terminated_instances:
        terminated_instances_ips = [
            instance.ip_address for instance in terminated_instances
        ]
        remove_ips_from_nginx_upstream_conf(terminated_instances_ips)


if __name__ == "__main__":
    management()
