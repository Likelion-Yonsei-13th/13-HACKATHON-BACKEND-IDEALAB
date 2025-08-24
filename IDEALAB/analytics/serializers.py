from rest_framework import serializers

class IndustryMetricItemSerializer(serializers.Serializer):
    trdar_cd = serializers.CharField()
    yyq = serializers.CharField(allow_null=True)
    year = serializers.IntegerField(allow_null=True)
    avg_sales = serializers.DecimalField(max_digits=18, decimal_places=4, allow_null=True)
    growth_rate = serializers.DecimalField(max_digits=10, decimal_places=4, allow_null=True)
    change_index = serializers.DecimalField(max_digits=10, decimal_places=4, allow_null=True)

class IndustryMetricResponseSerializer(serializers.Serializer):
    status = serializers.IntegerField()
    success = serializers.BooleanField()
    message = serializers.CharField()
    params = serializers.DictField()
    region = serializers.DictField()
    aggregate = serializers.DictField()
    items = IndustryMetricItemSerializer(many=True)


class ChangeIndexItemSerializer(serializers.Serializer):
    trdar_cd = serializers.CharField()
    yyq = serializers.CharField()
    change_index = serializers.DecimalField(max_digits=10, decimal_places=4, allow_null=True)

class ChangeIndexResponseSerializer(serializers.Serializer):
    status = serializers.IntegerField()
    success = serializers.BooleanField()
    message = serializers.CharField()
    params = serializers.DictField()
    region = serializers.DictField()
    aggregate = serializers.DictField()
    items = ChangeIndexItemSerializer(many=True)


class ClosureItemSerializer(serializers.Serializer):
    signgu_cd = serializers.CharField()
    year = serializers.IntegerField()
    category = serializers.CharField()
    count = serializers.IntegerField()

class ClosuresResponseSerializer(serializers.Serializer):
    status = serializers.IntegerField()
    success = serializers.BooleanField()
    message = serializers.CharField()
    params = serializers.DictField()
    region = serializers.DictField()
    aggregate = serializers.DictField()
    items = ClosureItemSerializer(many=True)
